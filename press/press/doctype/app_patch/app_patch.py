# Copyright (c) 2024, Frappe and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document
from frappe.model.naming import append_number_if_name_exists

from typing import TypedDict, Optional

PatchConfig = TypedDict(
	"PatchConfig",
	patch=Optional[str],
	patch_filename=str,
	patch_url=str,
	build_assets=bool,
	patch_bench=Optional[str],
	patch_all_benches=bool,
)


class AppPatch(Document):
	def validate(self):
		patches = frappe.get_all(
			"App Patch",
			fields=["name", "filename"],
			filters={"bench": self.bench, "patch": self.patch},
		)
		if not len(patches):
			return

		patch_name = patches[0].get("name")
		filename = patches[0].get("filename")
		frappe.throw(
			f"Patch already exists for {self.bench} by the filename {filename} and name {patch_name}"
		)

	def autoname(self):
		self.name = append_number_if_name_exists(
			"App Patch",
			f"{self.bench}-p",
			separator="",
		)

	def after_insert(self):
		# TODO: Call apply_patch
		pass

	@frappe.whitelist()
	def apply_patch(self):
		# TODO: AgentJob that applies patch
		pass

	@frappe.whitelist()
	def revert_patch(self):
		# TODO: Revert patch
		pass


def create_app_patch(
	release_group: str, app: str, patch_config: PatchConfig
) -> list[str]:
	patch = get_patch(patch_config)
	benches = get_benches(release_group, patch_config)
	patches = []

	for bench in benches:
		doc_dict = dict(
			doctype="AppPatch",
			patch=patch,
			bench=bench,
			group=release_group,
			app_release=get_app_release(bench, app),
			url=patch_config.get("patch_url"),
			filename=patch_config.get("patch_filename"),
			build_assets=patch_config.get("build_assets"),
		)

		app_patch: AppPatch = frappe.get_doc(doc_dict)
		app_patch.insert()
		patches.append(app_patch.name)

	return patches


def get_patch(patch_config: PatchConfig) -> str:
	if patch := patch_config.get("patch"):
		return patch

	patch_url = patch_config.get("patch_url")
	return requests.get(patch_url).text


def get_benches(release_group: str, patch_config: PatchConfig) -> list[str]:
	if not patch_config.get("patch_all_benches"):
		return [patch_config["patch_bench"]]

	return frappe.get_all(
		"Bench",
		filters={"status": "Active", "group": release_group},
		pluck="name",
	)


def get_app_release(bench: str, app: str) -> str:
	return frappe.get_all(
		"Bench App",
		filters={"parent": bench, "app": app},
		pluck="name",
	)[0]
