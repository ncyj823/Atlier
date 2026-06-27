import { useCallback, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import {
  useAudioRecorder,
  useAudioRecorderState,
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
} from "expo-audio";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

// VAD tuning
const SILENCE_DB = -42;       // metering threshold considered silence (lower = quieter)
const SILENCE_HOLD_MS = 1500; // need this much continuous silence to auto-stop
const MIN_RECORD_MS = 900;    // ignore silence in the first moment so a slow start doesn't kill it

type Opts = { onAutoStop?: (transcript: string) => void };

export function useVoiceCapture(opts: Opts = {}) {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY, undefined, 200);
  const state = useAudioRecorderState(recorder, 200);
  const [isRecording, setIsRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startedAtRef = useRef<number>(0);
  const silentSinceRef = useRef<number | null>(null);
  const stoppingRef = useRef(false);
  const onAutoStopRef = useRef(opts.onAutoStop);
  onAutoStopRef.current = opts.onAutoStop;

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

  const _doStopAndTranscribe = useCallback(async (): Promise<string | null> => {
    if (stoppingRef.current) return null;
    stoppingRef.current = true;
    try {
      await recorder.stop();
    } catch {}
    setIsRecording(false);

    const uri = recorder.uri;
    if (!uri) {
      stoppingRef.current = false;
      return null;
    }
    setTranscribing(true);
    try {
      const form = new FormData();
      if (Platform.OS === "web") {
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
      stoppingRef.current = false;
    }
  }, [recorder]);

  // VAD loop — auto-stop on sustained silence
  useEffect(() => {
    if (!isRecording) {
      silentSinceRef.current = null;
      return;
    }
    const metering = state?.metering;
    if (metering == null) return;
    const now = Date.now();
    if (now - startedAtRef.current < MIN_RECORD_MS) return;
    if (metering < SILENCE_DB) {
      if (silentSinceRef.current == null) silentSinceRef.current = now;
      else if (now - silentSinceRef.current >= SILENCE_HOLD_MS) {
        // auto-stop
        silentSinceRef.current = null;
        (async () => {
          const text = await _doStopAndTranscribe();
          if (text && onAutoStopRef.current) onAutoStopRef.current(text);
        })();
      }
    } else {
      silentSinceRef.current = null;
    }
  }, [state?.metering, isRecording, _doStopAndTranscribe]);

  const start = async () => {
    setError(null);
    const ok = await requestPerm();
    if (!ok) return;
    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
      startedAtRef.current = Date.now();
      silentSinceRef.current = null;
      setIsRecording(true);
    } catch (e: any) {
      setError(e?.message || "Could not start recording");
    }
  };

  const stopAndTranscribe = async (): Promise<string | null> => {
    if (!isRecording) return null;
    return _doStopAndTranscribe();
  };

  return { isRecording, transcribing, error, start, stopAndTranscribe, setError, metering: state?.metering };
}
