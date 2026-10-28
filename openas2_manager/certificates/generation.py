# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Create AS2 key pairs and public certificates for partner exchange.

Private keys are written only to PKCS12 files on disk. They are never stored
in DocType text fields or returned in API responses.
"""

from __future__ import annotations

import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import frappe
from frappe.utils import add_days, get_files_path, getdate, nowdate, today
from frappe.utils.file_manager import save_file
from frappe.utils.password import get_decrypted_password

ALIAS_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

KNOWN_OPENAS2_ROOTS = [
	Path("/mnt/c/Users/laksh/Downloads/OpenAS2A"),
	Path("/mnt/c/Users/laksh/Downloads/OpenAS2B"),
	Path("/mnt/c/Users/laksh/Downloads/OpenAS20"),
	Path("/mnt/c/Users/laksh/Downloads/OpenAS2C"),
]

WINDOWS_KEYTOOL_CANDIDATES = [
	Path("/mnt/c/Program Files/Eclipse Adoptium/jdk-17.0.19.10-hotspot/bin/keytool.exe"),
]


def inspect_generation_capability() -> dict:
	linux_keytool = shutil.which("keytool")
	linux_java = shutil.which("java")
	openssl = shutil.which("openssl")
	windows_keytool = next((str(p) for p in WINDOWS_KEYTOOL_CANDIDATES if p.is_file()), None)

	openas2_installs = []
	for root in KNOWN_OPENAS2_ROOTS:
		if not root.is_dir():
			continue
		config_xml = root / "config" / "config.xml"
		p12_files = (
			sorted(str(p) for p in (root / "config").glob("*.p12"))
			if (root / "config").is_dir()
			else []
		)
		openas2_installs.append(
			{
				"path": str(root),
				"config_xml": config_xml.is_file(),
				"pkcs12_keystores": p12_files,
			}
		)

	return {
		"openas2_certificate_format": "PKCS12 (.p12)",
		"openas2_factory": "org.openas2.cert.PKCS12CertificateFactory",
		"preferred_tool": "openssl (pkcs12) or Java keytool",
		"linux_keytool": linux_keytool,
		"linux_java": linux_java,
		"windows_keytool": windows_keytool,
		"openssl": openssl,
		"openas2_installs_found": openas2_installs,
		"can_generate": bool(openssl),
		"writes_to_openas2_store": False,
	}


def _safe_alias(alias: str) -> str:
	alias = (alias or "").strip()
	if not ALIAS_RE.match(alias):
		frappe.throw(
			frappe._(
				"X509 Alias must be 1–64 characters: letters, numbers, dot, underscore, hyphen."
			)
		)
	return alias


def _resolve_output_dir(doc) -> Path:
	"""Prefer instance config/certs_managed; else site private files."""
	if doc.openas2_instance and frappe.db.exists("OpenAS2 Instance", doc.openas2_instance):
		inst = frappe.get_doc("OpenAS2 Instance", doc.openas2_instance)
		home = (inst.openas2_home or "").strip()
		if home:
			out = Path(home).expanduser() / "config" / "certs_managed"
			out.mkdir(parents=True, exist_ok=True)
			return out

	site_private = Path(get_files_path(is_private=True)) / "as2_certs" / doc.name
	site_private.mkdir(parents=True, exist_ok=True)
	return site_private


def _run(cmd: list[str], *, input_text: str | None = None) -> None:
	proc = subprocess.run(
		cmd,
		input=input_text,
		text=True,
		capture_output=True,
		check=False,
	)
	if proc.returncode != 0:
		err = (proc.stderr or proc.stdout or "").strip()
		# Never include password material; commands don't echo -passin in stderr usually.
		frappe.throw(frappe._("Certificate tool failed: {0}").format(err[:800] or "unknown error"))


def _fingerprint_sha256(cert_path: Path, inform: str = "PEM") -> str | None:
	openssl = shutil.which("openssl")
	if not openssl or not cert_path.is_file():
		return None
	proc = subprocess.run(
		[
			openssl,
			"x509",
			"-inform",
			inform,
			"-in",
			str(cert_path),
			"-noout",
			"-fingerprint",
			"-sha256",
		],
		capture_output=True,
		text=True,
		check=False,
	)
	if proc.returncode != 0:
		return None
	line = (proc.stdout or "").strip()
	if "=" in line:
		return line.split("=", 1)[1].strip()
	return line or None


def _attach_public_cer(doc_name: str, cer_path: Path) -> str:
	content = cer_path.read_bytes()
	file_doc = save_file(
		fname=cer_path.name,
		content=content,
		dt="AS2 Certificate",
		dn=doc_name,
		is_private=0,
	)
	return file_doc.file_url


@frappe.whitelist()
def generate_own_keypair(name: str) -> dict:
	"""Generate PKCS12 (private+public) and attach public .cer for partner exchange."""
	if not name:
		frappe.throw(frappe._("AS2 Certificate name is required."))

	doc = frappe.get_doc("AS2 Certificate", name)
	doc.check_permission("write")

	if doc.purpose != "Own Key Pair":
		frappe.throw(frappe._("Purpose must be Own Key Pair to generate a private/public key pair."))

	openssl = shutil.which("openssl")
	if not openssl:
		frappe.throw(
			frappe._(
				"OpenSSL was not found on this server. Install openssl to generate certificates."
			)
		)

	alias = _safe_alias(doc.x509_alias)
	cn = (doc.common_name or "").strip()
	if not cn:
		frappe.throw(frappe._("Common Name (CN) is required."))

	org = (doc.organization or doc.owner_type or "OpenAS2").strip()
	days = int(doc.validity_days or 825)
	if days < 1 or days > 3650:
		frappe.throw(frappe._("Validity Days must be between 1 and 3650."))

	key_size = str(doc.key_size or "2048")
	if key_size not in ("2048", "4096"):
		key_size = "2048"

	password = None
	try:
		password = get_decrypted_password("AS2 Certificate", doc.name, "keystore_password")
	except Exception:
		password = None
	if not password:
		password = secrets.token_urlsafe(18)
		doc.keystore_password = password

	out_dir = _resolve_output_dir(doc)
	p12_path = out_dir / f"{alias}.p12"
	cer_path = out_dir / f"{alias}.cer"

	subj = f"/CN={cn}/O={org}"

	with tempfile.TemporaryDirectory(prefix="as2cert_") as tmp:
		tmp_path = Path(tmp)
		key_pem = tmp_path / "key.pem"
		cert_pem = tmp_path / "cert.pem"

		_run(
			[
				openssl,
				"req",
				"-x509",
				"-newkey",
				f"rsa:{key_size}",
				"-sha256",
				"-days",
				str(days),
				"-nodes",
				"-keyout",
				str(key_pem),
				"-out",
				str(cert_pem),
				"-subj",
				subj,
			]
		)

		_run(
			[
				openssl,
				"pkcs12",
				"-export",
				"-inkey",
				str(key_pem),
				"-in",
				str(cert_pem),
				"-name",
				alias,
				"-out",
				str(p12_path),
				"-passout",
				f"pass:{password}",
			]
		)

		# Public cert only for exchange (DER .cer preferred for Windows partners).
		_run(
			[
				openssl,
				"x509",
				"-in",
				str(cert_pem),
				"-outform",
				"DER",
				"-out",
				str(cer_path),
			]
		)

		# Ensure private key material is gone with temp dir.
		key_pem.unlink(missing_ok=True)

	file_url = _attach_public_cer(doc.name, cer_path)
	fingerprint = _fingerprint_sha256(cer_path, inform="DER")

	doc.keystore_path = str(p12_path)
	doc.private_key_stored = 1
	doc.certificate_file = file_url
	doc.public_cert_fingerprint = fingerprint
	doc.valid_from = getdate(today())
	doc.valid_until = getdate(add_days(nowdate(), days))
	doc.status = "Active"
	doc.exchange_status = "Ready to Share"
	doc.generation_notes = (
		f"Generated PKCS12 at {p12_path}. "
		"Private key is only inside the .p12 file. "
		"Download/share the Public Certificate File (.cer) with your partner."
	)
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"ok": True,
		"certificate": doc.name,
		"keystore_path": doc.keystore_path,
		"public_certificate_file": doc.certificate_file,
		"fingerprint": doc.public_cert_fingerprint,
		"exchange_status": doc.exchange_status,
		"private_key_returned": False,
		"message": frappe._(
			"Key pair created. Private key is in the .p12 on disk only. "
			"Use the Public Certificate File to exchange with your partner."
		),
	}


@frappe.whitelist()
def mark_public_shared(name: str, partner: str | None = None) -> dict:
	"""Record that the public certificate was shared with a partner."""
	doc = frappe.get_doc("AS2 Certificate", name)
	doc.check_permission("write")
	if not doc.certificate_file:
		frappe.throw(frappe._("Attach or generate a Public Certificate File first."))
	if partner:
		doc.exchange_partner = partner
	doc.exchange_status = "Shared With Partner"
	if not doc.exchange_notes:
		doc.exchange_notes = frappe._(
			"Public certificate shared. Partner must import it into their OpenAS2 keystore "
			"with alias matching your x509_alias on their side."
		)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {
		"ok": True,
		"exchange_status": doc.exchange_status,
		"partner": doc.exchange_partner,
		"public_certificate_file": doc.certificate_file,
		"message": frappe._("Marked as shared with partner. They need only your public .cer."),
	}


@frappe.whitelist()
def import_partner_public_certificate(name: str) -> dict:
	"""Validate a Partner Public Certificate attachment and mark imported."""
	doc = frappe.get_doc("AS2 Certificate", name)
	doc.check_permission("write")

	if doc.purpose != "Partner Public Certificate":
		frappe.throw(frappe._("Set Purpose to Partner Public Certificate to import a partner cert."))
	if not doc.certificate_file:
		frappe.throw(frappe._("Attach the partner's public .cer / .crt / .pem first, then Save."))

	# Resolve attached file path
	file_url = doc.certificate_file
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(frappe._("Could not find the attached public certificate file."))

	file_doc = frappe.get_doc("File", file_name)
	path = file_doc.get_full_path()
	cert_path = Path(path)
	if not cert_path.is_file():
		frappe.throw(frappe._("Attached certificate file is missing on disk."))

	openssl = shutil.which("openssl")
	fingerprint = None
	if openssl:
		# Accept PEM or DER
		for form in ("PEM", "DER"):
			proc = subprocess.run(
				[openssl, "x509", "-inform", form, "-in", str(cert_path), "-noout", "-subject"],
				capture_output=True,
				text=True,
				check=False,
			)
			if proc.returncode == 0:
				fingerprint = _fingerprint_sha256(cert_path) if form == "PEM" else None
				if fingerprint is None:
					# try fingerprint with matching inform
					fp = subprocess.run(
						[
							openssl,
							"x509",
							"-inform",
							form,
							"-in",
							str(cert_path),
							"-noout",
							"-fingerprint",
							"-sha256",
						],
						capture_output=True,
						text=True,
						check=False,
					)
					if fp.returncode == 0 and "=" in (fp.stdout or ""):
						fingerprint = fp.stdout.split("=", 1)[1].strip()
				break
		else:
			frappe.throw(frappe._("Attached file is not a valid X.509 public certificate."))

	doc.public_cert_fingerprint = fingerprint
	doc.private_key_stored = 0
	doc.keystore_path = ""
	doc.status = "Active"
	doc.exchange_status = "Partner Cert Imported"
	doc.generation_notes = (
		"Partner public certificate imported. "
		"Import this .cer into your OpenAS2 keystore with the partner's x509_alias. "
		"No private key is stored for partner certificates."
	)
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"ok": True,
		"fingerprint": doc.public_cert_fingerprint,
		"exchange_status": doc.exchange_status,
		"private_key_returned": False,
		"message": frappe._(
			"Partner public certificate recorded. Import the public file into your OpenAS2 .p12 "
			"using their alias — never request their private key."
		),
	}


@frappe.whitelist()
def request_certificate_generation(name: str) -> dict:
	"""Back-compat Desk button → generate own key pair when purpose allows."""
	doc = frappe.get_doc("AS2 Certificate", name)
	if doc.purpose == "Own Key Pair":
		return generate_own_keypair(name)
	return import_partner_public_certificate(name)
