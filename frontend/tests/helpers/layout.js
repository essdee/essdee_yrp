import { getLockedDepartment } from "../../src/router/departmentLock.js"

/** Builds the minimal Registered Experience ui_config a site layout returns. */
export const layoutConfig = (experienceKey, workspaces) => ({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: experienceKey }, config: { experience_props: { workspaces } } } })

/** Locks the department to a layout that lists only the given workspaces. */
export const lockedDepartment = (experienceKey, workspaces) => getLockedDepartment(layoutConfig(experienceKey, workspaces))
