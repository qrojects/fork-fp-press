# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import dns.resolver

import frappe
from press.press.doctype.agent_job.agent_job import job_detail
from press.utils import log_error, get_current_team


@frappe.whitelist()
def new(site):
	team = get_current_team()
	bench = frappe.get_all(
		"Bench",
		fields=["name", "server"],
		filters={"status": "Active", "group": site["group"]},
		order_by="creation desc",
		limit=1,
	)[0].name
	site = frappe.get_doc(
		{
			"doctype": "Site",
			"subdomain": site["name"],
			"bench": bench,
			"apps": [{"app": app} for app in site["apps"]],
			"enable_scheduled_backups": site["backups"],
			"enable_uptime_monitoring": site["monitor"],
			"team": team,
		},
	).insert(ignore_permissions=True)
	return site.name


@frappe.whitelist()
def jobs(name):
	jobs = frappe.get_all(
		"Agent Job",
		fields=["name", "job_type", "creation", "status", "start", "end", "duration"],
		filters={"site": name},
		limit=10,
	)
	return jobs


@frappe.whitelist()
def job(name):
	job = frappe.get_doc("Agent Job", name)
	job = job.as_dict()
	job.steps = frappe.get_all(
		"Agent Job Step",
		filters={"agent_job": name},
		fields=["step_name", "status", "start", "end", "duration", "output", "traceback"],
		order_by="creation",
	)
	return job


@frappe.whitelist()
def running_jobs(name):
	jobs = frappe.get_all(
		"Agent Job", filters={"status": ("in", ("Pending", "Running")), "site": name}
	)
	return [job_detail(job.name) for job in jobs]


@frappe.whitelist()
def backups(name):
	backups = frappe.get_all(
		"Site Backup",
		fields=["name", "`database`", "size", "url", "creation", "status"],
		filters={"site": name},
		limit=5,
	)
	return backups


@frappe.whitelist()
def domains(name):
	domains = frappe.get_all(
		"Site Domain", fields=["name", "domain"], filters={"site": name}
	)
	return domains


@frappe.whitelist()
def activities(name):
	activities = frappe.get_all(
		"Site Activity",
		fields=["action", "creation", "owner"],
		filters={"site": name},
		limit=5,
	)
	return activities


@frappe.whitelist()
def options_for_new():
	group = frappe.get_doc("Release Group", {"default": True})
	apps = frappe.get_all(
		"Frappe App",
		fields=["name", "frappe", "branch", "scrubbed", "url"],
		filters={"name": ("in", [row.app for row in group.apps])},
	)
	order = {row.app: row.idx for row in group.apps}
	return {
		"domain": frappe.db.get_single_value("Press Settings", "domain"),
		"group": group.name,
		"apps": sorted(apps, key=lambda x: order[x.name]),
	}


@frappe.whitelist()
def all():
	sites = frappe.get_list(
		"Site", fields=["name", "status", "modified"], order_by="creation desc"
	)
	return sites


@frappe.whitelist()
def get(name):
	site = frappe.get_doc("Site", name)
	apps = [app.app for app in site.apps]
	apps = frappe.get_all(
		"Frappe App",
		fields=["name", "repo_owner as owner", "scrubbed as repo", "url", "branch"],
		filters={"name": ("in", apps)},
	)
	return {
		"name": site.name,
		"status": site.status,
		"installed_apps": apps,
		"creation": site.creation,
		"last_updated": site.modified,
	}


@frappe.whitelist()
def analytics(name, period="1 hour"):
	interval, divisor, = {
		"1 hour": ("1 HOUR", 60),
		"6 hours": ("6 HOUR", 5 * 60),
		"24 hours": ("24 HOUR", 30 * 60),
		"7 days": ("7 DAY", 3 * 60 * 60),
		"30 days": ("30 DAY", 12 * 60 * 60),
	}[period]

	def get_data(doctype, fields):
		query = f"""
			SELECT
				{fields},
				FROM_UNIXTIME({divisor} * (UNIX_TIMESTAMP(timestamp) DIV {divisor})) as _timestamp
			FROM
				`tab{doctype}`
			WHERE
				site = %s AND timestamp >= UTC_TIMESTAMP() - INTERVAL {interval}
			GROUP BY
				_timestamp
		"""
		result = frappe.db.sql(query, name, as_dict=True, debug=False)
		for row in result:
			row["timestamp"] = row.pop("_timestamp")
		return result

	request_data = get_data(
		"Site Request Log", "COUNT(name) as request_count, SUM(duration) as request_duration"
	)
	job_data = get_data(
		"Site Job Log", "COUNT(name) as job_count, SUM(duration) as job_duration"
	)
	uptime_data = get_data(
		"Site Uptime Log",
		"AVG(web) AS web, AVG(scheduler) AS scheduler, AVG(socketio) AS socketio",
	)
	return {
		"request_count": [
			{"value": r.request_count, "timestamp": r.timestamp} for r in request_data
		],
		"request_cpu_time": [
			{"value": r.request_duration, "timestamp": r.timestamp} for r in request_data
		],
		"job_count": [{"value": r.job_count, "timestamp": r.timestamp} for r in job_data],
		"job_cpu_time": [
			{"value": r.job_duration, "timestamp": r.timestamp} for r in job_data
		],
		"uptime": uptime_data,
	}


@frappe.whitelist()
def login(name):
	return frappe.get_doc("Site", name).login()


@frappe.whitelist()
def backup(name):
	frappe.get_doc("Site", name).backup()


@frappe.whitelist()
def archive(name):
	frappe.get_doc("Site", name).archive()


@frappe.whitelist()
def exists(subdomain):
	return bool(frappe.db.exists("Site", {"subdomain": subdomain}))


@frappe.whitelist()
def setup_wizard_complete(name):
	return frappe.get_doc("Site", name).setup_wizard_complete()


@frappe.whitelist()
def check_dns(name, domain):
	try:
		answer = dns.resolver.query(domain, "CNAME")[0].to_text()
		mapped_domain = answer.rsplit(".", 1)[0]
		if mapped_domain == name:
			return True
	except Exception:
		log_error("DNS Query Exception", site=name, domain=domain)
	return False


@frappe.whitelist()
def add_domain(name, domain):
	frappe.get_doc("Site", name).add_domain(domain)


def update_config(name, config):
	print(name, config)
	return
	frappe.get_doc("Site", name).update_site_config(config)
