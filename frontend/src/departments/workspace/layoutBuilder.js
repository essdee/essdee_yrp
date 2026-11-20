import { CARD_CATALOGUE } from "../cardCatalogue.js"
import { departments } from "../registry.js"

let sectionKey = 0
const newSection = (label, cards = []) => ({ key: ++sectionKey, label, cards: [...cards] })

/** Editable copy of a builder layout `{ name, sections }`, or a new layout with one empty section. */
export function createDraft(layout = null) {
	return {
		department: "",
		hasOverride: false,
		originalName: layout?.name || "",
		title: layout?.name || "",
		sections: layout ? layout.sections.map((section) => newSection(section.label, section.cards)) : [newSection("Main")],
	}
}

/** Editable copy of built-in department layout `{ name, experience_key, workspaces, sections }`: its saved sections, else its current cards in one section. */
export function createDepartmentDraft(layout) {
	const department = departments.find((item) => item.key === layout.experience_key)
	const cards = CARD_CATALOGUE.filter((entry) => entry.department === department && layout.workspaces.includes(entry.card.key)).map((entry) => entry.id)
	const sections = layout.sections || [{ label: department.label, cards }]
	return {
		department: layout.experience_key,
		hasOverride: Boolean(layout.sections),
		originalName: layout.name,
		title: layout.name,
		sections: sections.map((section) => newSection(section.label, section.cards)),
	}
}

export function addSection(draft, label = "New section") {
	draft.sections.push(newSection(label))
}

export function removeSection(draft, index) {
	draft.sections.splice(index, 1)
}

function findCard(draft, id) {
	for (const [section, { cards }] of draft.sections.entries()) {
		const index = cards.indexOf(id)
		if (index >= 0) return { section, index }
	}
	return null
}

/** Moves the card at `from` to drop position `to` (an index in the list before the move). */
export function moveCard(draft, from, to) {
	const [id] = draft.sections[from.section].cards.splice(from.index, 1)
	const index = from.section === to.section && to.index > from.index ? to.index - 1 : to.index
	draft.sections[to.section].cards.splice(index, 0, id)
}

/** Places catalogue card `id` in a section at `position` (end by default), moving it if already placed. */
export function addCard(draft, section, id, position = draft.sections[section].cards.length) {
	const placed = findCard(draft, id)
	if (placed) moveCard(draft, placed, { section, index: position })
	else draft.sections[section].cards.splice(position, 0, id)
}

export function removeCard(draft, section, index) {
	draft.sections[section].cards.splice(index, 1)
}

/** Up (-1) or down (1) one step; past a section's edge the card joins the end or start of the neighbour section. */
export function moveCardBy(draft, section, index, step) {
	const cards = draft.sections[section].cards
	const target = index + step
	if (target >= 0 && target < cards.length) {
		[cards[index], cards[target]] = [cards[target], cards[index]]
		return
	}
	const neighbour = section + step
	if (neighbour < 0 || neighbour >= draft.sections.length) return
	moveCard(draft, { section, index }, { section: neighbour, index: step < 0 ? draft.sections[neighbour].cards.length : 0 })
}

/** Messages that block saving `draft`; `reservedNames` are the built-in layout names. */
export function getDraftProblems(draft, reservedNames = []) {
	const title = draft.title.trim()
	const problems = []
	if (!title) problems.push("Enter a layout title.")
	else if (!draft.department && reservedNames.includes(title)) problems.push(`${title} is a built-in layout name.`)
	if (!draft.sections.length) problems.push("Add at least one section.")
	if (draft.sections.some((section) => !section.label.trim())) problems.push("Every section needs a name.")
	for (const section of draft.sections) {
		if (section.label.trim() && !section.cards.length) problems.push(`Section ${section.label.trim()} has no cards.`)
	}
	return problems
}

/** Arguments for `save_department_override` (department draft) or `save_layout`. */
export function getPayload(draft) {
	const sections = JSON.stringify(draft.sections.map((section) => ({ label: section.label.trim(), cards: [...section.cards] })))
	if (draft.department) return { layout: draft.originalName, sections }
	return { title: draft.title.trim(), sections, original_name: draft.originalName }
}

/** Catalogue entries matching every word of `query`, grouped by department; `placed` ids are flagged. */
export function getCatalogueGroups(query = "", placed = new Set()) {
	const words = query.toLowerCase().split(/\s+/).filter(Boolean)
	const matches = (entry) => words.every((word) => entry.label.toLowerCase().includes(word))
	return departments
		.map((department) => ({
			department,
			entries: CARD_CATALOGUE.filter((entry) => entry.department === department && matches(entry)).map((entry) => ({ ...entry, placed: placed.has(entry.id) })),
		}))
		.filter((group) => group.entries.length)
}
