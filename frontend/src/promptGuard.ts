const INJECTION = [
  /ignore (all )?(previous|prior|above) (instructions|prompts)/i,
  /disregard (all )?(previous|prior|above)/i,
  /you are now /i,
  /system prompt/i,
  /jailbreak/i,
  /<(system|assistant)>/i,
  /reveal (your |the )?(system|hidden) (prompt|instructions)/i,
];

export function promptInjectionWarning(text: string): string | null {
  return INJECTION.some((pattern) => pattern.test(text))
    ? "This text looks like a prompt-injection attempt. Use a normal call transcript."
    : null;
}
