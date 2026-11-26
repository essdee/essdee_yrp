from unittest import TestCase

import frappe

from essdee_yrp.valuation_tree.traced_fifo import NEGATIVE, UNTRACED, TracedFifo, same_queue


def row(name, qty, rate=0, value=0, voucher_type="YRP Stock Entry", **extra):
	return frappe._dict(
		name=name,
		qty=qty,
		rate=rate,
		voucher_type=voucher_type,
		stock_value_difference=value,
		lot="L1",
		received_type="Accepted",
		**extra,
	)


class TestTracedFifo(TestCase):
	def test_takes_match_ledger_value(self):
		fifo = TracedFifo().replay([row("R1", 1.5, 200), row("R2", 1.5, 250), row("I1", -3, value=-675)])
		self.assertEqual(fifo.takes["I1"], [("R1", 1.5, 300.0), ("R2", 1.5, 375.0)])
		self.assertEqual(fifo.mismatches, {})

	def test_same_rate_receipts_stay_separate_sources(self):
		fifo = TracedFifo().replay([row("R1", 2, 200), row("R2", 2, 200), row("I1", -3, value=-600)])
		self.assertEqual(fifo.takes["I1"], [("R1", 2, 400), ("R2", 1, 200)])

	def test_adjusted_receipt_uses_effective_rate(self):
		fifo = TracedFifo().replay(
			[row("R1", 3, 200, valuation_adjustment_value=75), row("I1", -3, value=-675)]
		)
		self.assertEqual(fifo.takes["I1"], [("R1", 3, 675.0)])

	def test_negative_stock_take_is_residual_leaf(self):
		fifo = TracedFifo().replay([row("R1", 1, 100), row("I1", -3, value=-300, outgoing_rate=100)])
		self.assertEqual(fifo.takes["I1"], [("R1", 1, 100), (NEGATIVE, 2, 200)])
		self.assertEqual(fifo.queue, [[-2, 100, NEGATIVE]])

	def test_receipt_absorbs_negative_bin(self):
		fifo = TracedFifo().replay(
			[row("I1", -2, value=-200, outgoing_rate=100), row("R1", 5, 120), row("I2", -3, value=-360)]
		)
		self.assertEqual(fifo.takes["I2"], [("R1", 3, 360)])

	def test_reconciliation_resets_layers(self):
		rows = [
			row("R1", 4, 100),
			row("S1", 0, 150, voucher_type="YRP Stock Reconciliation", qty_after_transaction=4),
			row("I1", -2, value=-300),
		]
		fifo = TracedFifo().replay(rows)
		self.assertEqual(fifo.takes["I1"], [("S1", 2, 300)])

	def test_ledger_mismatch_is_recorded_not_corrected(self):
		fifo = TracedFifo().replay([row("R1", 1, 100), row("I1", -1, value=-150)])
		self.assertAlmostEqual(fifo.mismatches["I1"], 50)

	def test_resync_adopts_stored_queue_and_keeps_matching_sources(self):
		rows = [
			row("R1", 12, 106.56, stock_queue="[[12, 106.56]]"),
			row("R2", 2, 106.56, stock_queue="[[2, 106.56]]"),
			row("R3", 5, 16, stock_queue="[[2, 106.56], [5, 16], [1, 9]]"),
			row("I1", -8, value=-(2 * 106.56 + 5 * 16 + 9)),
		]
		fifo = TracedFifo().replay(rows)
		self.assertEqual([take[0] for take in fifo.takes["I1"]], ["R2", "R3", UNTRACED])
		self.assertEqual(fifo.mismatches, {})

	def test_same_queue_merges_adjacent_equal_rates(self):
		self.assertTrue(same_queue([[1, 5, "A"], [2, 5, "B"]], [[3, 5]]))
		self.assertFalse(same_queue([[1, 5, "A"]], [[1, 6]]))
