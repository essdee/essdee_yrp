<template>
	<Teleport to="body">
		<div
			v-if="content"
			ref="card"
			class="lvt-hover"
			role="tooltip"
			:style="{ top: `${position.top}px`, left: `${position.left}px` }"
		>
			<strong class="lvt-hover__title">{{ content.title }}</strong>
			<span v-if="content.subtitle" class="lvt-hover__subtitle">{{ content.subtitle }}</span>
			<template v-for="(row, index) in content.rows" :key="index">
				<hr v-if="row.divider" />
				<div v-else class="lvt-hover__row" :class="{ 'lvt-hover__row--strong': row.strong }">
					<span>{{ row.label }}</span>
					<span>{{ row.value }}</span>
				</div>
			</template>
			<p v-for="note in content.notes || []" :key="note" class="lvt-hover__note">{{ note }}</p>
		</div>
	</Teleport>
</template>

<script setup>
import { inject } from "vue"

/** The one styled hover card of the Valuation tab; state comes from `provideValuationHover()`. */
const { content, position, card } = inject("valuationHover")
</script>
