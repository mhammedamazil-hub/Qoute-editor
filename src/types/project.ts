import type { AnyElement, BackgroundFill } from './elements';

export interface CanvasSpec {
  width: number;
  height: number;
  background: BackgroundFill;
}

export interface SceneDocument {
  canvas: CanvasSpec;
  elements: AnyElement[];
}

export interface ProjectFile {
  version: 1;
  id: string;
  name: string;
  canvas: CanvasSpec;
  elements: AnyElement[];
  assets: Record<string, string>;
  metadata: {
    createdAt: number;
    updatedAt: number;
    app: 'quotecraft';
  };
}

export interface ProjectSummary {
  id: string;
  name: string;
  updatedAt: number;
  width: number;
  height: number;
  elementCount: number;
}

export interface CanvasPreset {
  id: string;
  label: string;
  hint: string;
  width: number;
  height: number;
}

export const CANVAS_PRESETS: CanvasPreset[] = [
  { id: 'ig-square', label: 'Instagram Square', hint: '1:1', width: 1080, height: 1080 },
  { id: 'ig-portrait', label: 'Instagram Portrait', hint: '4:5', width: 1080, height: 1350 },
  { id: 'ig-story', label: 'Instagram Story', hint: '9:16', width: 1080, height: 1920 },
  { id: 'yt-thumb', label: 'YouTube Thumbnail', hint: '16:9', width: 1920, height: 1080 },
  { id: 'poster', label: 'Poster', hint: '3:4', width: 1200, height: 1600 },
  { id: 'photo', label: 'Photo', hint: '3:2', width: 1800, height: 1200 },
  { id: 'wallpaper', label: 'Wallpaper', hint: '9:16', width: 1440, height: 2560 },
];
