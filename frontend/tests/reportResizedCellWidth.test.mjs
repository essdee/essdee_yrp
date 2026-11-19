import assert from "node:assert/strict"
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import test from "node:test"

const SOURCE = new URL("../src/", import.meta.url).pathname

function vueFiles(directory) {
	return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
		const path = join(directory, entry.name)
		if (entry.isDirectory()) return vueFiles(path)
		return entry.name.endsWith(".vue") ? [path] : []
	})
}

function cssRules(source) {
	const styles = [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(match => match[1]).join("\n")
	const css = styles.replace(/\/\*[\s\S]*?\*\//g, "").replace(/@media[^{]*\{/g, "")
	return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({ selector: selector.trim(), body }))
}

/** Report tables whose cell content is capped at a fixed width that a resized column would not lift. */
function fixedCellCaps(path) {
	return cssRules(readFileSync(path, "utf8"))
		.filter(rule => /\b(td|th)\b/.test(rule.selector) && /max-width\s*:\s*[\d.]+(px|rem|em|ch)/.test(rule.body))
		.filter(rule => !rule.selector.includes(":not(.is-column-sized)"))
		.map(rule => `${path.replace(SOURCE, "")}: ${rule.selector}`)
}

const reportTables = vueFiles(SOURCE).filter(path => /class="[^"]*\breport-table\b/.test(readFileSync(path, "utf8")))

test("report tables are found for the cell width check", () => {
	for (const name of ["StockBalanceReport.vue", "DeskBackedReport.vue", "CutBundleBalanceReport.vue"]) {
		assert.ok(reportTables.some(path => path.endsWith(name)), name)
	}
})

test("a resized report column lets its cell text use the new width", () => {
	assert.deepEqual(reportTables.flatMap(fixedCellCaps), [])
})

test("stock balance keeps its default text cap before any resize", () => {
	const rules = cssRules(readFileSync(join(SOURCE, "components/reports/StockBalanceReport.vue"), "utf8"))
	const capped = rules.find(rule => rule.selector.startsWith(".stock-table:not(.is-column-sized) td span"))
	assert.match(capped?.body || "", /max-width:\s*300px/)
	const ellipsis = rules.find(rule => rule.selector === ".stock-table td span:not(.multiline-cell)")
	assert.match(ellipsis.body, /text-overflow:\s*ellipsis/)
	assert.doesNotMatch(ellipsis.body, /max-width/)
})

test("sized report cells clip with an ellipsis at the column edge", () => {
	const css = readFileSync(join(SOURCE, "styles/reportTables.css"), "utf8")
	assert.match(css, /table\.is-column-sized > :is\(thead, tbody, tfoot\) > tr > :is\(th, td\) \{\s*overflow: hidden;\s*text-overflow: ellipsis;/)
})
