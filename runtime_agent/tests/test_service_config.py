# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Tests for Runtime Agent Windows Service packaging (no service install required)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

RUNTIME_AGENT = Path(__file__).resolve().parents[1]
SERVICE_DIR = RUNTIME_AGENT / "service"
XML_PATH = SERVICE_DIR / "OpenAS2RuntimeAgent.xml"
ENV_EXAMPLE = RUNTIME_AGENT / "agent.env.example"


def parse_agent_env(text: str) -> dict[str, str]:
	"""Parse KEY=VALUE lines the same way run_agent_for_service.ps1 expects."""
	result: dict[str, str] = {}
	for raw in text.splitlines():
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		if "=" not in line:
			continue
		name, value = line.split("=", 1)
		name = name.strip()
		value = value.strip()
		if (value.startswith('"') and value.endswith('"')) or (
			value.startswith("'") and value.endswith("'")
		):
			value = value[1:-1]
		result[name] = value
	return result


class TestRuntimeAgentServicePackaging(unittest.TestCase):
	def test_required_service_scripts_exist(self):
		required = [
			"Install-RuntimeAgentService.ps1",
			"Uninstall-RuntimeAgentService.ps1",
			"Start-RuntimeAgentService.ps1",
			"Stop-RuntimeAgentService.ps1",
			"Restart-RuntimeAgentService.ps1",
			"Get-RuntimeAgentServiceStatus.ps1",
			"run_agent_for_service.ps1",
			"_service_common.ps1",
			"OpenAS2RuntimeAgent.xml",
		]
		for name in required:
			path = SERVICE_DIR / name
			self.assertTrue(path.is_file(), f"missing {path}")

	def test_agent_py_unchanged_entry_still_present(self):
		agent = (RUNTIME_AGENT / "agent.py").read_text(encoding="utf-8")
		self.assertIn("OPENAS2_AGENT_TOKEN", agent)
		self.assertIn('if __name__ == "__main__"', agent)
		self.assertIn("9475", agent)

	def test_start_agent_ps1_still_manual_fallback(self):
		ps1 = (RUNTIME_AGENT / "start_agent.ps1").read_text(encoding="utf-8")
		self.assertIn("OPENAS2_AGENT_TOKEN", ps1)
		self.assertIn("0.0.0.0", ps1)
		self.assertIn("9475", ps1)

	def test_winsw_xml_service_name_and_no_token(self):
		xml = XML_PATH.read_text(encoding="utf-8")
		self.assertIn("<name>OpenAS2 Runtime Agent</name>", xml)
		self.assertIn("<id>OpenAS2RuntimeAgent</id>", xml)
		self.assertIn("<startmode>Automatic</startmode>", xml)
		self.assertIn('action="restart"', xml)
		self.assertIn("run_agent_for_service.ps1", xml)
		self.assertIn("logs", xml)
		# Token must not be baked into the checked-in XML
		self.assertNotIn("OPENAS2_AGENT_TOKEN", xml)
		self.assertNotRegex(xml, r"phase2-dev-token")
		self.assertNotRegex(xml, re.compile(r"<env\b", re.I))

	def test_env_example_documents_token_without_live_secret_file(self):
		self.assertTrue(ENV_EXAMPLE.is_file())
		example = parse_agent_env(ENV_EXAMPLE.read_text(encoding="utf-8"))
		self.assertIn("OPENAS2_AGENT_TOKEN", example)
		self.assertNotEqual(example["OPENAS2_AGENT_TOKEN"], "")
		self.assertFalse((RUNTIME_AGENT / "agent.env").exists())

	def test_parse_agent_env_strips_quotes_and_comments(self):
		text = """
# comment
OPENAS2_AGENT_TOKEN="secret-value"
OPENAS2_AGENT_PORT=9475

OPENAS2_AGENT_HOST='0.0.0.0'
"""
		parsed = parse_agent_env(text)
		self.assertEqual(parsed["OPENAS2_AGENT_TOKEN"], "secret-value")
		self.assertEqual(parsed["OPENAS2_AGENT_PORT"], "9475")
		self.assertEqual(parsed["OPENAS2_AGENT_HOST"], "0.0.0.0")

	def test_install_script_writes_env_not_hardcoded_token(self):
		install = (SERVICE_DIR / "Install-RuntimeAgentService.ps1").read_text(encoding="utf-8")
		self.assertIn("Write-AgentEnvFile", install)
		self.assertIn("agent.env", install)
		self.assertIn("OpenAS2 Runtime Agent", install)
		self.assertNotIn("phase2-dev-token-change-me", install)

	def test_runner_loads_env_file_and_uses_existing_agent(self):
		runner = (SERVICE_DIR / "run_agent_for_service.ps1").read_text(encoding="utf-8")
		self.assertIn("Import-AgentEnvFile", runner)
		self.assertIn("agent.env", runner)
		self.assertIn("agent.py", runner)
		self.assertIn("0.0.0.0", runner)
		self.assertIn("9475", runner)


if __name__ == "__main__":
	unittest.main()
