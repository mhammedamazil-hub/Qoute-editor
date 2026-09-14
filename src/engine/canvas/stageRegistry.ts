import type Konva from 'konva';

let stage: Konva.Stage | null = null;
let contentGroupName = 'scene-content';

export function registerStage(s: Konva.Stage | null) {
  stage = s;
}
export function getStage() {
  return stage;
}
export function getContentGroup(): Konva.Group | null {
  if (!stage) return null;
  return (stage.findOne(`.${contentGroupName}`) as Konva.Group | undefined) ?? null;
}
export function setContentGroupName(name: string) {
  contentGroupName = name;
}
export const CONTENT_GROUP_NAME = contentGroupName;
