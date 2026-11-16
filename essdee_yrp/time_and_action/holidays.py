"""Company holiday calendar used by the Time and Action date engine."""

from dataclasses import dataclass
from datetime import date

import erpnext
import frappe
from frappe import _
from frappe.utils import formatdate, getdate


@dataclass(frozen=True)
class HolidayCalendar:
	"""Holiday dates of one Holiday List and the range that list covers."""

	dates: frozenset
	from_date: date
	to_date: date
	name: str = ""

	def __contains__(self, day):
		return day in self.dates

	def count_between(self, after: date, until: date) -> int:
		"""Holidays in (after, until]."""
		return sum(1 for day in self.dates if after < day <= until)

	def ensure_covers(self, day: date) -> None:
		if self.from_date <= day <= self.to_date:
			return
		frappe.throw(
			_("Holiday List {0} covers {1} to {2}. Extend it to cover {3}.").format(
				frappe.bold(self.name),
				formatdate(self.from_date, "dd-mm-yyyy"),
				formatdate(self.to_date, "dd-mm-yyyy"),
				formatdate(day, "dd-mm-yyyy"),
			)
		)


def get_company_holidays() -> HolidayCalendar:
	company = erpnext.get_default_company()
	if not company:
		frappe.throw(_("Set a default Company before scheduling Time and Action."))
	holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
	if not holiday_list:
		frappe.throw(_("Set a Default Holiday List on Company {0}.").format(frappe.bold(company)))
	from_date, to_date = frappe.db.get_value("Holiday List", holiday_list, ["from_date", "to_date"])
	days = frappe.get_all("Holiday", filters={"parent": holiday_list}, pluck="holiday_date")
	return HolidayCalendar(
		frozenset(getdate(day) for day in days), getdate(from_date), getdate(to_date), holiday_list
	)
