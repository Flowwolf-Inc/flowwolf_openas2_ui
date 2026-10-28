# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""X12 JSON conversion for Message Details."""

from __future__ import annotations

import json
import unittest

from openas2_manager.openas2.x12_json import (
	SUPPORTED_TRANSACTIONS,
	extract_edi_interchanges,
	x12_message_json,
)


def _interchange(body: str, element: str = "*", terminator: str = "~", component: str = ">") -> str:
	fields = [
		"00",
		"          ",
		"00",
		"          ",
		"ZZ",
		"SHIPPER        ",
		"ZZ",
		"BROKER         ",
		"260101",
		"1200",
		"U",
		"00401",
		"000000001",
		"0",
		"P",
		component,
	]
	isa = "ISA" + element + element.join(fields) + terminator
	if len(isa) != 106:
		raise AssertionError(len(isa))
	gs = element.join(["GS", "SM", "SHIPPER", "BROKER", "20260101", "1200", "1", "X", "004010"]) + terminator
	return isa + gs + body


def _txn(code: str, segments: list[str], element: str = "*", terminator: str = "~") -> str:
	count = 2 + len(segments)
	parts = [element.join(["ST", code, "0001"])] + segments
	parts.append(element.join(["SE", str(count), "0001"]))
	parts.append(element.join(["GE", "1", "1"]))
	parts.append(element.join(["IEA", "1", "000000001"]))
	return terminator.join(parts) + terminator


class TestX12MessageJson(unittest.TestCase):
	def test_supported_204_keeps_element_order_and_raw_text(self):
		raw = _interchange(_txn("204", ["B2**SCAC**LOAD1"]))
		original = raw
		result = x12_message_json(raw)
		self.assertEqual(raw, original)
		self.assertTrue(result["available"])
		self.assertEqual(result["transaction_type"], "204")
		self.assertNotIn("shipment_id", result["json"])
		parsed = json.loads(result["json"])
		self.assertEqual(parsed["format"], "X12")
		self.assertEqual(parsed["interchange"]["sender_id"], "SHIPPER")
		self.assertEqual(parsed["interchange"]["receiver_id"], "BROKER")
		segment = parsed["functional_groups"][0]["transactions"][0]["segments"][0]
		self.assertEqual(segment["id"], "B2")
		self.assertEqual(segment["elements"], ["", "SCAC", "", "LOAD1"])
		self.assertIn("B2**SCAC**LOAD1", original)

	def test_component_separator_comes_from_isa(self):
		raw = _interchange(_txn("214", ["N1*SH*ACME*ZZ*ID>EXTRA"]))
		parsed = json.loads(x12_message_json(raw)["json"])
		elements = parsed["functional_groups"][0]["transactions"][0]["segments"][0]["elements"]
		self.assertEqual(elements[3], ["ID", "EXTRA"])

	def test_pipe_delimiters_are_not_assumed(self):
		body = _txn("990", ["B1|LOAD9|20260101|A"], element="|", terminator="~")
		raw = _interchange(body, element="|", terminator="~")
		parsed = json.loads(x12_message_json(raw)["json"])
		self.assertEqual(parsed["transaction_type"], "990")
		self.assertEqual(parsed["delimiters"]["element"], "|")
		segment = parsed["functional_groups"][0]["transactions"][0]["segments"][0]
		self.assertEqual(segment["elements"], ["LOAD9", "20260101", "A"])

	def test_each_supported_transaction_converts(self):
		for code in SUPPORTED_TRANSACTIONS:
			result = x12_message_json(_interchange(_txn(code, [])))
			self.assertTrue(result["available"], code)
			self.assertEqual(result["transaction_type"], code)
			json.loads(result["json"])

	def test_each_type_keeps_its_own_segments_and_envelope(self):
		"""The approved JSON document is the X12 envelope plus that type's segments.

		No separate business schema is defined for these types. Segment ids and
		element positions stay on the transaction that contained them.
		"""
		samples = {
			"204": ["B2**SCAC**LOAD1", "B2A*00", "L11*LOAD1*BM"],
			"990": ["B1*SCAC*LOAD1*20260101*A"],
			"214": ["B10*SHIP1*LOAD1*SCAC", "AT7*X1*NS***20260101*1200"],
			"210": ["B3**INV1*LOAD1*CC**20260101*100"],
			"810": ["BIG*20260101*INV1", "TDS*10000"],
			"820": ["BPR*I*10.00", "TRN*1*PAY1"],
			"997": ["AK1*SM*1", "AK2*204*0001", "AK5*A", "AK9*A*1*1*1"],
		}
		parsed_by_type = {}
		for code, segments in samples.items():
			raw = _interchange(_txn(code, segments))
			original = raw
			result = x12_message_json(raw)
			self.assertEqual(raw, original, code)
			self.assertTrue(result["available"], code)
			self.assertEqual(result["transaction_type"], code)
			parsed = json.loads(result["json"])
			parsed_by_type[code] = parsed
			self.assertEqual(
				list(parsed),
				["format", "transaction_type", "delimiters", "interchange", "functional_groups"],
			)
			self.assertEqual(parsed["format"], "X12")
			self.assertEqual(parsed["transaction_type"], code)
			self.assertEqual(
				parsed["delimiters"],
				{"element": "*", "component": ">", "segment": "~"},
			)
			self.assertIsInstance(parsed["interchange"]["control_number"], str)
			group = parsed["functional_groups"][0]
			self.assertEqual(group["functional_identifier_code"], "SM")
			txn = group["transactions"][0]
			self.assertEqual(txn["transaction_set"], code)
			self.assertEqual(txn["control_number"], "0001")
			self.assertIsInstance(txn["segments"], list)
			ids = [segment["id"] for segment in txn["segments"]]
			self.assertEqual(ids, [segment.split("*", 1)[0] for segment in segments])
			for segment, source in zip(txn["segments"], segments, strict=True):
				self.assertEqual(list(segment), ["id", "elements"])
				self.assertEqual(segment["elements"], source.split("*")[1:])
			self.assertNotIn("shipment_id", result["json"])
			self.assertNotIn("segment_count", result["json"])

		for code, parsed in parsed_by_type.items():
			own_ids = {segment["id"] for segment in parsed["functional_groups"][0]["transactions"][0]["segments"]}
			for other, other_parsed in parsed_by_type.items():
				if other == code:
					continue
				other_ids = {
					segment["id"]
					for segment in other_parsed["functional_groups"][0]["transactions"][0]["segments"]
				}
				self.assertFalse(own_ids & other_ids, (code, other))

		mixed_body = (
			"ST*204*0001~B2**SCAC**LOAD1~SE*3*0001~"
			"ST*990*0002~B1*SCAC*LOAD1*20260101*A~SE*3*0002~"
			"GE*2*1~IEA*1*000000001~"
		)
		mixed = json.loads(x12_message_json(_interchange(mixed_body))["json"])
		self.assertEqual(mixed["transaction_type"], "")
		sets = [txn["transaction_set"] for txn in mixed["functional_groups"][0]["transactions"]]
		self.assertEqual(sets, ["204", "990"])
		self.assertEqual(mixed["functional_groups"][0]["transactions"][0]["segments"][0]["id"], "B2")
		self.assertEqual(mixed["functional_groups"][0]["transactions"][1]["segments"][0]["id"], "B1")

	def test_unsupported_transaction_does_not_invent_json(self):
		result = x12_message_json(_interchange(_txn("999", ["AK2*204*0001"])))
		self.assertFalse(result["available"])
		self.assertEqual(result["reason"], "unsupported")
		self.assertEqual(result["transaction_type"], "999")
		self.assertEqual(result["json"], "")
		self.assertIn("999", result["message"])
		self.assertNotIn("AK2", result["message"])

	def test_empty_invalid_and_incomplete_payloads(self):
		empty = x12_message_json("  ")
		self.assertEqual(empty["reason"], "empty")
		self.assertEqual(empty["json"], "")
		invalid = x12_message_json("<html><body>Not EDI</body></html>")
		self.assertEqual(invalid["reason"], "invalid")
		self.assertEqual(invalid["json"], "")
		self.assertNotIn("<html>", invalid["message"])
		partial = _interchange("ST*204*0001~B2**SCAC~")
		incomplete = x12_message_json(partial)
		self.assertEqual(incomplete["reason"], "incomplete")
		self.assertEqual(incomplete["json"], "")
		mismatch = _interchange(_txn("810", []).replace("SE*2*0001", "SE*2*9999"))
		self.assertEqual(x12_message_json(mismatch)["reason"], "incomplete")

	def test_json_text_is_formatted_and_downloadable(self):
		result = x12_message_json(_interchange(_txn("820", ["BPR*I*10.00"])))
		self.assertTrue(result["json"].startswith("{\n"))
		self.assertEqual(json.loads(result["json"])["transaction_type"], "820")

	def _mime_wrap(self, edi: str, encoding: str = "binary") -> str:
		return (
			"------=_Part_1\r\n"
			"Content-Type: application/edi-x12\r\n"
			f"Content-Transfer-Encoding: {encoding}\r\n"
			"\r\n"
			f"{edi}\r\n"
			"------=_Part_1\r\n"
			"Content-Type: application/pkcs7-signature; name=smime.p7s\r\n"
			"Content-Transfer-Encoding: base64\r\n"
			"\r\n"
			"U0lHTkFUVVJF\r\n"
			"------=_Part_1--\r\n"
		)

	def test_mime_wrapped_204_990_214_210_convert(self):
		from openas2_manager.openas2.remote_tracking import transaction_type_from_payload

		for code in ("204", "990", "214", "210"):
			edi = _interchange(_txn(code, ["N1*SH*ACME"]))
			wrapped = self._mime_wrap(edi)
			result = x12_message_json(wrapped)
			self.assertTrue(result["available"], code)
			self.assertEqual(result["transaction_type"], code)
			self.assertEqual(transaction_type_from_payload(wrapped), code)
			parsed = json.loads(result["json"])
			self.assertEqual(parsed["format"], "X12")
			self.assertNotIn("------", result["json"])
			self.assertNotIn("pkcs7", result["json"])
			self.assertNotIn("SIGNATURE", result["json"])

	def test_base64_and_newline_delimited_payloads_convert(self):
		import base64

		edi = _interchange(_txn("210", [], terminator="\n"), terminator="\n")
		self.assertEqual(x12_message_json(edi)["transaction_type"], "210")
		encoded = base64.b64encode(edi.encode()).decode()
		wrapped = (
			"Content-Type: application/EDI-X12\r\n"
			"Content-Transfer-Encoding: base64\r\n"
			"\r\n"
			+ encoded
		)
		result = x12_message_json(wrapped)
		self.assertTrue(result["available"], result["message"])
		self.assertEqual(result["transaction_type"], "210")
		self.assertNotIn(encoded[:24], result["json"])

	def test_raw_view_keeps_only_isa_through_iea(self):
		edi = _interchange(_txn("204", ["N1*SH*ACME"]))
		wrapped = self._mime_wrap(edi)
		found = extract_edi_interchanges(wrapped)
		self.assertEqual(found, [edi])
		self.assertTrue(found[0].startswith("ISA"))
		self.assertTrue(found[0].rstrip("\r\n").endswith("~"))
		self.assertIn("IEA*", found[0])
		self.assertNotIn("Content-Type", found[0])
		self.assertNotIn("Content-Transfer-Encoding", found[0])
		self.assertNotIn("Content-Disposition", found[0])
		self.assertNotIn("------", found[0])
		self.assertNotIn("pkcs7", found[0])

	def test_multiple_attachments_stay_separate(self):
		first = _interchange(_txn("204", ["N1*SH*ONE"]))
		second = _interchange(_txn("214", ["N1*SH*TWO"]))
		wrapped = (
			"------=_Part_A\r\n"
			"Content-Type: application/edi-x12\r\n"
			"Content-Transfer-Encoding: binary\r\n"
			"\r\n"
			f"{first}\r\n"
			"------=_Part_A\r\n"
			"Content-Type: application/edi-x12\r\n"
			"Content-Transfer-Encoding: binary\r\n"
			"\r\n"
			f"{second}\r\n"
			"------=_Part_A\r\n"
			"Content-Type: application/pkcs7-signature\r\n"
			"Content-Transfer-Encoding: base64\r\n"
			"\r\n"
			"U0lHTkFUVVJF\r\n"
			"------=_Part_A--\r\n"
		)
		found = extract_edi_interchanges(wrapped)
		self.assertEqual(found, [first, second])
		self.assertNotIn(second, first)
		joined = "\n\n".join(found)
		self.assertNotIn("Content-Type", joined)
		self.assertNotIn("U0lHTkFUVVJF", joined)
		result = x12_message_json(wrapped)
		self.assertTrue(result["available"])
		parsed = json.loads(result["json"])
		self.assertEqual([item["transaction_type"] for item in parsed], ["204", "214"])

	def test_mime_without_edi_extracts_nothing(self):
		wrapped = self._mime_wrap("Hello from the partner")
		self.assertEqual(extract_edi_interchanges(wrapped), [])
		result = x12_message_json(wrapped)
		self.assertFalse(result["available"])
		self.assertEqual(result["json"], "")
		self.assertNotIn("Hello", result["message"])
		self.assertNotIn("Content-Type", result["message"])

	def test_malformed_and_non_edi_do_not_invent_json(self):
		malformed = self._mime_wrap("ISA*NOT-A-COMPLETE-INTERCHANGE~\r\nST*204*0001~")
		broken = x12_message_json(malformed)
		self.assertFalse(broken["available"])
		self.assertEqual(broken["reason"], "invalid")
		self.assertEqual(broken["json"], "")
		self.assertIn("not a supported X12", broken["message"])
		for payload in (
			'{"transaction": "204", "body": "ST*204*0001"}',
			"AS2-From: SHIPPER\r\nAS2-To: BROKER\r\n\r\nnot edi",
			"Hello from the partner",
			"ST*204*0001~SE*2*0001~",
		):
			result = x12_message_json(payload)
			self.assertFalse(result["available"], payload)
			self.assertEqual(result["json"], "")
			self.assertNotIn(payload[:12], result["message"])
