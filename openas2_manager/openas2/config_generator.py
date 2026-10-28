# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Generate isolated OpenAS2 config files for a provisioned instance.

Phase 1:
- Writes config.xml, partnerships.xml, and supporting static files
- Enables HTTP AS2 receiver; HTTPS disabled until real certs exist
- Does not generate PKCS12/JKS material
- Does not start OpenAS2
"""

from __future__ import annotations

import secrets
from pathlib import Path
from xml.sax.saxutils import escape

import frappe

from openas2_manager.openas2.paths import assert_under_directory

# Static templates shipped with the app (not copied from live OpenAS20/A/B).
TEMPLATE_DIR = (
	Path(__file__).resolve().parent.parent / "templates" / "openas2_runtime"
)


def _secrets_password(nbytes: int = 18) -> str:
	"""Generate a random password for on-disk OpenAS2 properties only."""
	return secrets.token_urlsafe(nbytes)


def write_static_support_files(config_dir: Path, home: Path) -> list[str]:
	"""Copy non-secret support files from app templates into config/."""
	assert_under_directory(home, config_dir)
	written: list[str] = []
	mapping = {
		"commands.xml": "commands.xml",
		"logback.xml": "logback.xml",
		"messages.xml": "messages.xml",
		"content_type_mappings.properties": "content_type_mappings.properties",
		"emailtemplate.txt": "emailtemplate.txt",
	}
	for src_name, dest_name in mapping.items():
		src = TEMPLATE_DIR / src_name
		if not src.is_file():
			frappe.throw(frappe._("Missing OpenAS2 template file: {0}").format(src_name))
		dest = config_dir / dest_name
		dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
		written.append(dest_name)
	return written


def build_minimal_partnerships_xml(*, partner_name: str, as2_id: str, x509_alias: str) -> str:
	"""Local partner only — no remote partnerships until configured in Manager."""
	return (
		"<partnerships>\n"
		f'    <partner name="{escape(partner_name)}"\n'
		f'             as2_id="{escape(as2_id)}"\n'
		f'             x509_alias="{escape(x509_alias)}"\n'
		f'             email="as2msgs@{escape(as2_id.lower())}.local"/>\n'
		"</partnerships>\n"
	)


def build_config_xml(
	*,
	http_port: int,
	https_port: int,
	mdn_http_port: int,
	mdn_https_port: int,
	tracking_port: int,
	health_port: int,
	mdn_enabled: bool,
	as2_keystore_password: str,
	ssl_password: str,
	tracking_password: str,
) -> str:
	"""Instance-specific config.xml.

	HTTPS modules stay disabled until real keystores are provisioned (Phase 3).
	HTTP AS2 + MDN receivers are enabled so the instance is ready to start later
	once a PKCS12 keystore exists.
	"""
	mdn_http = "true" if mdn_enabled else "false"
	# Passwords are required by OpenAS2 schema; never returned by provisioning APIs.
	ks_pw = escape(as2_keystore_password, {"\"": "&quot;"})
	ssl_pw = escape(ssl_password, {"\"": "&quot;"})
	trk_pw = escape(tracking_password, {"\"": "&quot;"})

	return f"""<?xml version="1.0" encoding="UTF-8"?>
<openas2>
   <properties config.dir="%home%"
               storageBaseDir="%home%/../data"
               partnership_file="%home%/partnerships.xml"
               log_date_format="yyyy-MM-dd HH:mm:ss.SSS"
               sql_timestamp_format="yyyy-MM-dd HH:mm:ss.SSS"
               as2_message_id_format="$date.yyyyMMddHHmmssZ$-$rand.123$-$msg.sender.as2_id$_$msg.receiver.as2_id$_$msg.attributes.filename$"
               as2_receive_message_filename_fallback="$rand.shortUUID$"
               as2_async_mdn_url="http://localhost:$properties.async_mdn_receiver_port$"
               as2_keystore="%home%/../keystore/as2.p12"
               as2_keystore_password="{ks_pw}"
               as2_keystore.refresh_interval="300"
               ssl_trust_keystore.enabled="false"
               ssl_trust_keystore="%home%/../keystore/ssl_trust_certs.p12"
               ssl_trust_keystore_password="{ssl_pw}"
               ssl_trust_keystore.refresh_interval="300"
               ssl_keystore="%home%/../keystore/ssl_certs.jks"
               ssl_keystore_password="{ssl_pw}"
               console.command.processor.enabled="false"
               restapi.command.processor.enabled="false"
               restapi.command.processor.baseuri="http://localhost:8080"
               restapi.command.processor.userid="userID"
               restapi.command.processor.password="disabled"
               processor.resend_max_retries="5"
               module.AS2SenderModule.enabled="true"
               module.AS2SenderModule.readtimeout="60000"
               module.MDNSenderModule.enabled="true"
               module.DbTrackingModule.enabled="true"
               module.MDNFileModule.enabled="true"
               module.MDNFileModule.filename="$properties.storageBaseDir$/$mdn.msg.sender.as2_id$-$mdn.msg.receiver.as2_id$/mdn/$date.yyyy-MM-dd$/$mdn.msg.headers.message-id$"
               module.MDNFileModule.tempdir="$properties.storageBaseDir$/temp"
               module.MessageFileModule.enabled="true"
               module.MessageFileModule.filename="$properties.storageBaseDir$/$msg.sender.as2_id$-$msg.receiver.as2_id$/inbox/$msg.headers.message-id$"
               module.MessageFileModule.header="$properties.storageBaseDir$/$msg.sender.as2_id$-$msg.receiver.as2_id$/msgheaders/$date.yyyy-MM-dd$/$msg.headers.message-id$"
               module.MessageFileModule.tempdir="$properties.storageBaseDir$/temp"
               module.DirectoryResenderModule.enabled="true"
               module.DirectoryResenderModule.resenddelay="60"
               module.AS2ReceiverModule.http.enabled="true"
               module.AS2ReceiverModule.http.port="{http_port}"
               module.AS2MDNReceiverModule.http.enabled="{mdn_http}"
               module.AS2MDNReceiverModule.http.port="{mdn_http_port}"
               module.AS2ReceiverModule.https.enabled="false"
               module.AS2ReceiverModule.https.port="{https_port}"
               module.AS2MDNReceiverModule.https.enabled="false"
               module.AS2MDNReceiverModule.https.port="{mdn_https_port}"
               module.HealthCheckModule.enabled="false"
               module.HealthCheckModule.protocol="http"
               module.HealthCheckModule.address="localhost"
               module.HealthCheckModule.port="{health_port}"
               module.HealthCheckModule.keystore="$properties.ssl_keystore$"
               module.HealthCheckModule.keystore_password="$properties.ssl_keystore_password$"
               async_mdn_receiver_port="$properties.module.AS2MDNReceiverModule.http.port$"
               email.from="Open AS2 Server&lt;as2msgs@openas2.org&gt;"
               email.to="your email address"
               email.smtpserver="localhost"
               email.smtpport="25"
               email.smtpauth="false"
               email.smtpuser=""
               email.smtppwd=""
               email.subject="$exception.name$: $exception.message$"
               email.bodytemplate="%home%/emailtemplate.txt"
               msg_tracking.use_embedded_db="true"
               msg_tracking.force_load_jdbc_driver="false"
               msg_tracking.db_user="sa"
               msg_tracking.db_pwd="{trk_pw}"
               msg_tracking.db_name="openas2"
               msg_tracking.table_name="msg_metadata"
               msg_tracking.db_directory="%home%/DB"
               msg_tracking.jdbc_driver="org.h2.Driver"
               msg_tracking.jdbc_connect_string="jdbc:h2:$component.db_directory$/$component.db_name$"
               msg_tracking.sql_escape_character="'"
               msg_tracking.tcp_server_start="true"
               msg_tracking.tcp_server_port="{tracking_port}"
               msg_tracking.tcp_server_password="{trk_pw}"
               reject_unsigned_messages="false"
               pollerConfigBase.outboxdir="$properties.storageBaseDir$/outbox/$partnership.receiver.as2_id$"
               pollerConfigBase.errordir="$properties.storageBaseDir$/outbox/error/$date.YYYY$-$date.MM$-$date.dd$/$partnership.receiver.as2_id$"
               pollerConfigBase.interval="5"
               pollerConfigBase.defaults="sender.as2_id=$partnership.sender.as2_id$, receiver.as2_id=$partnership.receiver.as2_id$"
               pollerConfigBase.sendfilename="true"
               pollerConfigBase.mimetype="application/EDI-X12"
               pollerConfigBase.process_files_in_parallel="false"
               pollerConfigBase.max_parallel_files="20"
               pollerConfigBase.max_file_processing_time_minutes="30"
               partnerships.polling.interval="120"
               messages.enabled="false"
               messages.polling.interval="120"
             />
   <certificates classname="org.openas2.cert.PKCS12CertificateFactory"
                 identifier="as2_certs"
                 filename="$properties.as2_keystore$"
                 password="$properties.as2_keystore_password$"
                 interval="$properties.as2_keystore.refresh_interval$"/>
   <certificates enabled="$properties.ssl_trust_keystore.enabled$"
                 classname="org.openas2.cert.PKCS12CertificateFactory"
                 identifier="ssl_trust_certs"
                 filename="$properties.ssl_trust_keystore$"
                 password="$properties.ssl_trust_keystore_password$"
                 interval="$properties.ssl_trust_keystore.refresh_interval$"/>
   <commands classname="org.openas2.cmd.XMLCommandRegistry"
             filename="%home%/commands.xml"/>
   <commandProcessors>
      <commandProcessor classname="org.openas2.cmd.processor.StreamCommandProcessor"
                        enabled="$properties.console.command.processor.enabled$"/>
      <commandProcessor classname="org.openas2.cmd.processor.RestCommandProcessor"
                        enabled="$properties.restapi.command.processor.enabled$"
                        baseuri="$properties.restapi.command.processor.baseuri$"
                        ssl_protocol="TLS"
                        ssl_keystore="$properties.ssl_keystore$"
                        ssl_keystore_password="$properties.ssl_keystore_password$"
                        userid="$properties.restapi.command.processor.userid$"
                        password="$properties.restapi.command.processor.password$" />
   </commandProcessors>
   <processor classname="org.openas2.processor.DefaultProcessor"
              pendingMDN="$properties.storageBaseDir$/pendingMDN3"
              pendingMDNinfo="$properties.storageBaseDir$/pendinginfoMDN3"
              resend_max_retries="$properties.processor.resend_max_retries$">
      <module enabled="$properties.module.AS2SenderModule.enabled$"
              classname="org.openas2.processor.sender.AS2SenderModule"
              readtimeout="$properties.module.AS2SenderModule.readtimeout$" />
      <module enabled="$properties.module.MDNSenderModule.enabled$"
              classname="org.openas2.processor.sender.MDNSenderModule"/>
      <module enabled="$properties.module.DbTrackingModule.enabled$"
              classname="org.openas2.processor.msgtracking.DbTrackingModule"
              use_embedded_db="$properties.msg_tracking.use_embedded_db$"
              force_load_jdbc_driver="$properties.msg_tracking.force_load_jdbc_driver$"
              db_user="$properties.msg_tracking.db_user$"
              db_pwd="$properties.msg_tracking.db_pwd$"
              db_name="$properties.msg_tracking.db_name$"
              table_name="$properties.msg_tracking.table_name$"
              db_directory="$properties.msg_tracking.db_directory$"
              jdbc_driver="$properties.msg_tracking.jdbc_driver$"
              jdbc_connect_string="$properties.msg_tracking.jdbc_connect_string$"
              sql_escape_character="$properties.msg_tracking.sql_escape_character$"
              tcp_server_start="$properties.msg_tracking.tcp_server_start$"
              tcp_server_port="$properties.msg_tracking.tcp_server_port$"
              tcp_server_password="$properties.msg_tracking.tcp_server_password$"/>
      <module enabled="$properties.module.MDNFileModule.enabled$"
              classname="org.openas2.processor.storage.MDNFileModule"
              filename="$properties.module.MDNFileModule.filename$"
              protocol="as2"
              tempdir="$properties.module.MDNFileModule.tempdir$"/>
      <module enabled="$properties.module.MessageFileModule.enabled$"
              classname="org.openas2.processor.storage.MessageFileModule"
              filename="$properties.module.MessageFileModule.filename$"
              header="$properties.module.MessageFileModule.header$"
              protocol="as2"
              tempdir="$properties.module.MessageFileModule.tempdir$"/>
      <module enabled="$properties.module.AS2ReceiverModule.http.enabled$"
              classname="org.openas2.processor.receiver.AS2ReceiverModule"
              port="$properties.module.AS2ReceiverModule.http.port$"
              errordir="$properties.storageBaseDir$/inbox/error"
              errorformat="sender.as2_id, receiver.as2_id, headers.message-id"/>
      <module enabled="$properties.module.AS2ReceiverModule.https.enabled$"
              classname="org.openas2.processor.receiver.AS2ReceiverModule"
              port="$properties.module.AS2ReceiverModule.https.port$"
              protocol="https"
              ssl_protocol="TLS"
              ssl_keystore="$properties.ssl_keystore$"
              ssl_keystore_password="$properties.ssl_keystore_password$"
              errordir="$properties.storageBaseDir$/inbox/error"
              errorformat="sender.as2_id, receiver.as2_id, headers.message-id"/>
      <module enabled="$properties.module.AS2MDNReceiverModule.http.enabled$"
              classname="org.openas2.processor.receiver.AS2MDNReceiverModule"
              port="$properties.async_mdn_receiver_port$"/>
      <module enabled="$properties.module.AS2MDNReceiverModule.https.enabled$"
              classname="org.openas2.processor.receiver.AS2MDNReceiverModule"
              port="$properties.module.AS2MDNReceiverModule.https.port$"
              protocol="https"
              ssl_protocol="TLS"
              ssl_keystore="$properties.ssl_keystore$"
              ssl_keystore_password="$properties.ssl_keystore_password$"/>
      <module enabled="$properties.module.DirectoryResenderModule.enabled$"
              classname="org.openas2.processor.resender.DirectoryResenderModule"
              resenddir="$properties.storageBaseDir$/resend"
              errordir="$properties.storageBaseDir$/resend/error"
              resenddelay="$properties.module.DirectoryResenderModule.resenddelay$"/>
      <module enabled="$properties.module.HealthCheckModule.enabled$"
              classname="org.openas2.processor.receiver.HealthCheckModule"
              protocol="$properties.module.HealthCheckModule.protocol$"
              address="$properties.module.HealthCheckModule.address$"
              port="$properties.module.HealthCheckModule.port$"
              ssl_keystore="$properties.ssl_keystore$"
              ssl_keystore_password="$properties.ssl_keystore_password$"/>
   </processor>
   <pollerConfigBase classname="org.openas2.processor.receiver.AS2DirectoryPollingModule"
           outboxdir="$properties.pollerConfigBase.outboxdir$"
           errordir="$properties.pollerConfigBase.errordir$"
           interval="$properties.pollerConfigBase.interval$"
           defaults="$properties.pollerConfigBase.defaults$"
           sendfilename="$properties.pollerConfigBase.sendfilename$"
           mimetype="$properties.pollerConfigBase.mimetype$"
           process_files_in_parallel="$properties.pollerConfigBase.process_files_in_parallel$"
           max_parallel_files="$properties.pollerConfigBase.max_parallel_files$"
           max_file_processing_time_minutes="$properties.pollerConfigBase.max_file_processing_time_minutes$" />
   <partnerships classname="org.openas2.partner.XMLPartnershipFactory"
                 filename="$properties.partnership_file$"
                 interval="$properties.partnerships.polling.interval$"/>
   <messages enabled="$properties.messages.enabled$"
             classname="org.openas2.message.XMLMessageFactory"
             filename="%home%/messages.xml"
             interval="$properties.messages.polling.interval$"/>
</openas2>
"""


def generate_instance_secrets() -> dict[str, str]:
	"""Create random on-disk secrets (never returned to Desk UI)."""
	return {
		"as2_keystore_password": _secrets_password(),
		"ssl_password": _secrets_password(),
		"tracking_password": _secrets_password(),
	}
