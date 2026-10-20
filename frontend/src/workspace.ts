const KEY = 'classecho.workspace.v1'
export type WorkspaceSelection = { courseId: string; lectureId: string }

export function readWorkspace(): WorkspaceSelection {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    return {
      courseId: typeof value?.courseId === 'string' && value.courseId.length <= 80 ? value.courseId : '',
      lectureId: typeof value?.lectureId === 'string' && value.lectureId.length <= 80 ? value.lectureId : '',
    }
  } catch { return { courseId: '', lectureId: '' } }
}

export function saveWorkspace(selection: WorkspaceSelection) {
  try { localStorage.setItem(KEY, JSON.stringify({ courseId: selection.courseId, lectureId: selection.lectureId })) } catch { /* Storage restrictions must not prevent use of the app. */ }
}
