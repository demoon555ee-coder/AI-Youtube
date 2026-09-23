import React from "react";
import {
  AbsoluteFill,
  CanvasImage,
  Composition,
  Easing,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {Audio} from "@remotion/media";
import type {Caption} from "@remotion/captions";

type SceneAsset = {
  kind: "video" | "image" | "color";
  src?: string;
  color?: string;
};

type CaptionStyle = "standard" | "highlight" | "minimal";
type AppCaption = Caption & {style?: CaptionStyle};

type Scene = {
  scene: number;
  durationFrames: number;
  asset: SceneAsset;
  audioSrc?: string;
  onScreenText: string;
  motion?: string;
  transition?: string;
  captionStyle?: CaptionStyle;
  caption?: AppCaption;
};

export type RenderManifest = {
  compositionId: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  scenes: Scene[];
  captions: AppCaption[];
};

const fitMediaStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  objectFit: "cover",
};

const textStyle: React.CSSProperties = {
  position: "absolute",
  left: 80,
  right: 80,
  top: "50%",
  transform: "translateY(-50%)",
  textAlign: "center",
  color: "white",
  fontFamily: "DejaVu Sans, Arial, sans-serif",
  fontWeight: 800,
  fontSize: 64,
  lineHeight: 1.05,
  textShadow: "0 4px 18px rgba(0,0,0,0.75)",
  whiteSpace: "pre-wrap",
};

const captionBoxStyle: React.CSSProperties = {
  position: "absolute",
  left: 100,
  right: 100,
  bottom: 58,
  display: "flex",
  justifyContent: "center",
  padding: "12px 22px",
  borderRadius: 18,
  background: "rgba(0,0,0,0.58)",
  color: "white",
  fontFamily: "DejaVu Sans, Arial, sans-serif",
  fontSize: 34,
  fontWeight: 700,
  lineHeight: 1.18,
  textAlign: "center",
  textShadow: "0 2px 7px rgba(0,0,0,0.75)",
};

const captionStyles: Record<CaptionStyle, React.CSSProperties> = {
  standard: {
    background: "rgba(0,0,0,0.58)",
    color: "white",
    fontSize: 34,
    padding: "12px 22px",
    borderRadius: 18,
  },
  highlight: {
    background: "rgba(255,255,255,0.92)",
    color: "black",
    fontSize: 38,
    padding: "10px 24px",
    borderRadius: 14,
    textShadow: "none",
  },
  minimal: {
    background: "transparent",
    color: "white",
    fontSize: 28,
    padding: "4px 8px",
    borderRadius: 0,
    textShadow: "0 2px 7px rgba(0,0,0,0.85)",
  },
};

const sceneColors = [
  "#111827",
  "#1e293b",
  "#312e81",
  "#064e3b",
  "#7c2d12",
  "#27272a",
];

const pickColor = (index: number): string =>
  sceneColors[(index - 1) % sceneColors.length];

const SceneLayer: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const fadeInEnd = Math.max(1, Math.min(10, Math.floor(scene.durationFrames / 3)));
  const fadeOutStart = Math.max(fadeInEnd, scene.durationFrames - 10);
  const fadeIn = interpolate(frame, [0, fadeInEnd], [0, 1], {
    easing: Easing.inOut(Easing.ease),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(frame, [fadeOutStart, scene.durationFrames], [1, 0], {
    easing: Easing.inOut(Easing.ease),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fade = Math.min(fadeIn, fadeOut);
  const scale = interpolate(frame, [0, scene.durationFrames], [1.02, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const motion = scene.motion ?? "slow_push_in";
  const pan = interpolate(frame, [0, scene.durationFrames], [0, motion.includes("left") ? -28 : motion.includes("right") ? 28 : 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const zoom = motion.includes("zoom") || motion.includes("push") ? scale : 1;
  const mediaTransform = `translateX(${pan}px) scale(${zoom})`;
  const transition = (scene.transition ?? "cut").toLowerCase();
  const transitionFade = transition === "cut" ? 1 : fade;

  return (
    <AbsoluteFill style={{opacity: transitionFade}}>
      {scene.asset.kind === "video" && scene.asset.src ? (
        <OffthreadVideo
          src={staticFile(scene.asset.src)}
          muted
          loop
          style={{...fitMediaStyle, transform: mediaTransform}}
        />
      ) : scene.asset.kind === "image" && scene.asset.src ? (
        <CanvasImage
          src={staticFile(scene.asset.src)}
          style={{...fitMediaStyle, transform: mediaTransform}}
        />
      ) : (
        <AbsoluteFill style={{backgroundColor: scene.asset.color ?? pickColor(scene.scene)}} />
      )}

      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.12) 0%, rgba(0,0,0,0.28) 50%, rgba(0,0,0,0.62) 100%)",
        }}
      />

      {scene.onScreenText ? <div style={textStyle}>{scene.onScreenText}</div> : null}

      {scene.audioSrc ? (
        <Audio src={staticFile(scene.audioSrc)} volume={1} />
      ) : null}
    </AbsoluteFill>
  );
};

const CaptionTrack: React.FC<{captions: AppCaption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = (frame / fps) * 1000;
  const active = captions.find((caption) => nowMs >= caption.startMs && nowMs < caption.endMs);

  if (!active) {
    return null;
  }

  const style = active.style ?? "standard";
  return (
    <div
      style={{
        ...captionBoxStyle,
        ...captionStyles[style],
        ...(active.text.length > 80 ? {fontSize: style === "minimal" ? 24 : 30} : {}),
      }}
    >
      {active.text}
    </div>
  );
};

export const MainComposition: React.FC<RenderManifest> = (props) => {
  let cursor = 0;

  return (
    <AbsoluteFill style={{backgroundColor: "#000"}}>
      {props.scenes.map((scene) => {
        const from = cursor;
        cursor += scene.durationFrames;
        return (
          <Sequence key={`scene-${scene.scene}`} from={from} durationInFrames={scene.durationFrames}>
            <SceneLayer scene={scene} />
          </Sequence>
        );
      })}
      <CaptionTrack captions={props.captions} />
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="YouTubeAIVideo"
      component={MainComposition}
      durationInFrames={150}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{
        compositionId: "YouTubeAIVideo",
        width: 1920,
        height: 1080,
        fps: 30,
        durationInFrames: 150,
        scenes: [],
        captions: [],
      }}
      calculateMetadata={({props}) => ({
        durationInFrames: props.durationInFrames,
        fps: props.fps,
        width: props.width,
        height: props.height,
      })}
    />
  );
};
