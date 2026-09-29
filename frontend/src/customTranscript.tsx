import { useEffect, useState, type DragEvent, type ChangeEvent } from "react";
import { checkCustomTranscript } from "./api";
import { promptInjectionWarning } from "./promptGuard";

type Props = {
  value: string;
  onChange: (text: string) => void;
};

export function CustomTranscript({ value, onChange }: Props) {
  const [draft, setDraft] = useState(value);
  const [fileName, setFileName] = useState("");
  const [over, setOver] = useState(false);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    setDraft(value);
    if (!value) {
      setFileName("");
      setError("");
    }
  }, [value]);

  const applyTyped = (text: string) => {
    setDraft(text);
    const warning = promptInjectionWarning(text);
    setError(warning ?? "");
    if (warning) return;
    onChange(text);
  };

  const applyFile = (text: string, name: string) => {
    setDraft(text);
    const injection = promptInjectionWarning(text);
    if (injection) {
      setError(injection);
      return;
    }
    setChecking(true);
    setError("");
    void checkCustomTranscript(text)
      .then((warning) => {
        if (warning) {
          setError(warning);
          return;
        }
        setFileName(name);
        onChange(text);
      })
      .finally(() => setChecking(false));
  };

  const readFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".txt")) {
      setError("Please drop a .txt file.");
      return;
    }
    void file.text().then((text) => applyFile(text, file.name));
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file) readFile(file);
  };

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) readFile(file);
  };

  return (
    <div className="custom-transcript">
      <label
        className={over ? "file-drop is-over" : "file-drop"}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <input accept=".txt,text/plain" hidden type="file" onChange={onPick} disabled={checking} />
        <strong>Click or drop a .txt file</strong>
        <span>{checking ? "Checking this is a healthcare call…" : fileName || "Plain-text call transcript only"}</span>
      </label>

      <label className="custom-text">
        <span>Or type a transcript</span>
        <textarea
          spellCheck={false}
          value={draft}
          onChange={(event) => applyTyped(event.target.value)}
          placeholder="Paste or type the call transcript here."
        />
      </label>

      {error ? <p className="custom-error">{error}</p> : null}
    </div>
  );
}
