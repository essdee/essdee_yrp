import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingMarkerDialog.vue", import.meta.url), "utf8")

test("marker piece weight is read-only and previewed from the IPD", () => {
	assert.doesNotMatch(source, /v-model="form\.required_piece_weight"/)
	assert.match(source, /:model-value="piecePreview\.weight \?\? form\.required_piece_weight"[^>]*readonly disabled/)
	assert.match(source, /markerMethod\("preview_marker_piece_weight"\)/)
	assert.match(source, /JSON\.stringify\(\[canEdit\.value, form\.selected_type, form\.panels, form\.ratio_items\]\)/)
})
