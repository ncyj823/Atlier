import { useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import {
  useAudioRecorder,
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
} from "expo-audio";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

export function useVoiceCapture() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [isRecording, setIsRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastDoneRef = useRef(0);

  useEffect(() => {
    (async () => {
      try {
        if (Platform.OS !== "web") {
          await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        }
      } catch {}
    })();
  }, []);

  const requestPerm = async (): Promise<boolean> => {
    if (Platform.OS === "web") return true;
    const cur = await AudioModule.getRecordingPermissionsAsync();
    if (cur.granted) return true;
    if (!cur.canAskAgain) {
      setError("Microphone permission denied. Enable it in Settings.");
      return false;
    }
    const r = await AudioModule.requestRecordingPermissionsAsync();
    return !!r.granted;
  };

  const start = async () => {
    setError(null);
    const ok = await requestPerm();
    if (!ok) return;
    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
      setIsRecording(true);
    } catch (e: any) {
      setError(e?.message || "Could not start recording");
    }
  };

  const stopAndTranscribe = async (): Promise<string | null> => {
    if (!isRecording) return null;
    // Debounce double-taps
    if (Date.now() - lastDoneRef.current < 400) return null;
    lastDoneRef.current = Date.now();

    try {
      await recorder.stop();
    } catch {}
    setIsRecording(false);

    const uri = recorder.uri;
    if (!uri) {
      setError("Recording failed");
      return null;
    }
    setTranscribing(true);
    try {
      const form = new FormData();
      const isWeb = Platform.OS === "web";
      if (isWeb) {
        const res = await fetch(uri);
        const blob = await res.blob();
        const ext = (blob.type.split("/")[1] || "webm").split(";")[0];
        form.append("audio", new File([blob], `voice.${ext}`, { type: blob.type }));
      } else {
        const name = uri.split("/").pop() || "voice.m4a";
        const ext = name.split(".").pop() || "m4a";
        form.append("audio", { uri, name, type: `audio/${ext}` } as any);
      }
      const r = await fetch(`${BASE}/api/transcribe`, { method: "POST", body: form });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      return (data.text || "").trim();
    } catch (e: any) {
      setError(e?.message || "Transcription failed");
      return null;
    } finally {
      setTranscribing(false);
    }
  };

  return { isRecording, transcribing, error, start, stopAndTranscribe, setError };
}
