/**
 * Synthetic desk painter for replay sessions without a camera.
 *
 * Draws a stylized desk whose objects move exactly like the backend replay
 * provider expects (same phase math), so returned detection boxes visibly
 * lock onto the painted objects. Pixels are also scored server-side for
 * quality, so the painting includes real contrast and texture.
 */

import type { FrameSource } from "./frames";

// Tuned for a 30 fps capture cadence (roughly the same real-time motion speed
// as the original 10 fps replay, without three-times-faster synthetic motion).
const PHASE_SPEED = 0.012;

type PaintedObject = {
  label: "cup" | "book" | "phone";
  index: number;
  hue: string;
  shadow: string;
};

const OBJECTS: PaintedObject[] = [
  { label: "cup", index: 0, hue: "#c8b49a", shadow: "#7d6c58" },
  { label: "book", index: 1, hue: "#87a5b8", shadow: "#4e6572" },
  { label: "phone", index: 2, hue: "#39413f", shadow: "#171c1b" },
];

export function objectCenter(
  index: number,
  sequence: number,
  width: number,
  height: number,
): { x: number; y: number } {
  const phase = sequence * PHASE_SPEED + index * 1.9;
  return {
    x: width * (0.25 + index * 0.22) + Math.sin(phase) * width * 0.06,
    y: height * (0.42 + index * 0.08) + Math.sin(phase * 0.7) * height * 0.03,
  };
}

export function createSyntheticDesk(): FrameSource & {
  advance: () => void;
} {
  let sequence = 0;
  return {
    nativeWidth: 640,
    nativeHeight: 360,
    advance() {
      sequence += 1;
    },
    draw(context, width, height) {
      // Desk surface: warm gradient with grain bands for contrast.
      const surface = context.createLinearGradient(0, 0, 0, height);
      surface.addColorStop(0, "#2a2622");
      surface.addColorStop(0.35, "#3a332c");
      surface.addColorStop(1, "#241f1b");
      context.fillStyle = surface;
      context.fillRect(0, 0, width, height);

      context.save();
      context.globalAlpha = 0.18;
      context.strokeStyle = "#54483b";
      context.lineWidth = 2;
      for (let i = 0; i < 14; i += 1) {
        const y = (height / 14) * i + Math.sin(i * 3.7) * 6;
        context.beginPath();
        context.moveTo(0, y);
        context.bezierCurveTo(width * 0.3, y + 8, width * 0.7, y - 8, width, y);
        context.stroke();
      }
      context.restore();

      // Ambient key light from the upper left.
      const light = context.createRadialGradient(
        width * 0.22,
        height * 0.12,
        40,
        width * 0.22,
        height * 0.12,
        width * 0.9,
      );
      light.addColorStop(0, "rgba(255, 244, 214, 0.16)");
      light.addColorStop(1, "rgba(0, 0, 0, 0.22)");
      context.fillStyle = light;
      context.fillRect(0, 0, width, height);

      for (const item of OBJECTS) {
        const { x, y } = objectCenter(item.index, sequence, width, height);
        const w = Math.max(32, width * (0.12 - item.index * 0.015));
        const h = Math.max(32, height * (0.22 - item.index * 0.02));

        context.save();
        // Contact shadow.
        context.fillStyle = "rgba(0,0,0,0.35)";
        context.beginPath();
        context.ellipse(x, y + h * 0.46, w * 0.52, h * 0.12, 0, 0, Math.PI * 2);
        context.fill();

        if (item.label === "cup") {
          context.fillStyle = item.hue;
          context.beginPath();
          context.roundRect(x - w * 0.32, y - h * 0.4, w * 0.64, h * 0.8, 10);
          context.fill();
          context.strokeStyle = item.shadow;
          context.lineWidth = 5;
          context.beginPath();
          context.arc(x + w * 0.42, y - h * 0.05, w * 0.2, -0.9, 0.9);
          context.stroke();
          context.fillStyle = "rgba(30, 24, 18, 0.85)";
          context.beginPath();
          context.ellipse(x, y - h * 0.4, w * 0.32, h * 0.07, 0, 0, Math.PI * 2);
          context.fill();
        } else if (item.label === "book") {
          context.translate(x, y);
          context.rotate(Math.sin(sequence * PHASE_SPEED * 0.4) * 0.08 - 0.06);
          context.fillStyle = item.shadow;
          context.fillRect(-w * 0.5, -h * 0.34, w, h * 0.68);
          context.fillStyle = item.hue;
          context.fillRect(-w * 0.5, -h * 0.34, w * 0.94, h * 0.62);
          context.fillStyle = "rgba(240, 236, 226, 0.85)";
          context.fillRect(-w * 0.38, -h * 0.22, w * 0.56, h * 0.05);
          context.fillRect(-w * 0.38, -h * 0.1, w * 0.44, h * 0.05);
        } else {
          context.translate(x, y);
          context.fillStyle = item.hue;
          context.beginPath();
          context.roundRect(-w * 0.28, -h * 0.42, w * 0.56, h * 0.84, 12);
          context.fill();
          const screen = context.createLinearGradient(0, -h * 0.4, 0, h * 0.4);
          screen.addColorStop(0, "#20302f");
          screen.addColorStop(1, "#101817");
          context.fillStyle = screen;
          context.beginPath();
          context.roundRect(-w * 0.23, -h * 0.36, w * 0.46, h * 0.72, 8);
          context.fill();
          context.fillStyle = "rgba(181, 242, 231, 0.5)";
          context.fillRect(-w * 0.16, -h * 0.26, w * 0.2, 3);
          context.fillRect(-w * 0.16, -h * 0.18, w * 0.28, 3);
        }
        context.restore();
      }

      // Subtle sensor vignette + noise so quality metrics look organic.
      const vignette = context.createRadialGradient(
        width / 2,
        height / 2,
        height * 0.35,
        width / 2,
        height / 2,
        height * 0.85,
      );
      vignette.addColorStop(0, "rgba(0,0,0,0)");
      vignette.addColorStop(1, "rgba(0,0,0,0.34)");
      context.fillStyle = vignette;
      context.fillRect(0, 0, width, height);
      return true;
    },
  };
}

export function videoFrameSource(video: HTMLVideoElement): FrameSource {
  const captureI420: FrameSource["captureI420"] =
    typeof globalThis.VideoFrame === "function"
      ? async (width, height) => {
          if (
            video.readyState < 2 ||
            video.videoWidth !== width ||
            video.videoHeight !== height
          ) {
            return null;
          }
          const frame = new globalThis.VideoFrame(video, {
            timestamp: Math.round(performance.now() * 1000),
          });
          try {
            const yBytes = width * height;
            const chromaBytes = yBytes / 4;
            const i420 = new Uint8Array(yBytes + chromaBytes * 2);
            await frame.copyTo(i420, {
              format: "I420",
              layout: [
                { offset: 0, stride: width },
                { offset: yBytes, stride: width / 2 },
                { offset: yBytes + chromaBytes, stride: width / 2 },
              ],
            });
            return i420;
          } finally {
            frame.close();
          }
        }
      : undefined;
  return {
    get nativeWidth() {
      return video.videoWidth || 1280;
    },
    get nativeHeight() {
      return video.videoHeight || 720;
    },
    draw(context, width, height) {
      if (video.readyState < 2 || video.videoWidth === 0) {
        return false;
      }
      context.drawImage(video, 0, 0, width, height);
      return true;
    },
    ...(captureI420 === undefined ? {} : { captureI420 }),
  };
}
