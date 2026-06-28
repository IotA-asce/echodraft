import type { Scene } from "../../api";
import { formatStructureStatus } from "../../lib/format";

export function SceneList({ scenes, onOpen }: { scenes: Scene[]; onOpen: (scene: Scene) => void }) {
  return (
    <div>
      {scenes.map((scene, index) => (
        <button className="tree-button" type="button" key={scene.id} onClick={() => onOpen(scene)}>
          Scene {index + 1}
          <small>
            {formatStructureStatus(scene.status, scene.confidence)}
            {scene.userLocked ? " · locked" : ""}
          </small>
        </button>
      ))}
    </div>
  );
}
