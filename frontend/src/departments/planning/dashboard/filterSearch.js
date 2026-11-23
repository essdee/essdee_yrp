const SEPARATORS = /[,;\n]/

/** Options whose value or hint contains a single search term, an exact value first (a pasted list shows all), then picks outside the options. */
export function searchOptions(options, search, selected) {
	const text = search.trim().toLowerCase()
	const isExact = (option) => String(option.value).toLowerCase() === text
	const matching = text && !SEPARATORS.test(text)
		? options.filter((option) => `${option.value} ${option.hint || ""}`.toLowerCase().includes(text)).sort((a, b) => isExact(b) - isExact(a))
		: options
	const known = new Set(matching.map((option) => option.value))
	return [...matching, ...selected.filter((value) => !known.has(value)).map((value) => ({ value, hint: "" }))]
}

/** Selection after Enter: the first suggestion of one term, or every exact match of a pasted list; null when nothing matches. */
export function enterValues(options, search, selected) {
	const wanted = new Set(search.split(SEPARATORS).map((value) => value.trim().toLowerCase()).filter(Boolean))
	if (!wanted.size) return null
	const matches = SEPARATORS.test(search)
		? options.map((option) => option.value).filter((value) => wanted.has(String(value).toLowerCase()))
		: searchOptions(options, search, []).slice(0, 1).map((option) => option.value)
	return matches.length ? [...new Set([...selected, ...matches])] : null
}
