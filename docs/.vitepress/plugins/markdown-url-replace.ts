import type { Plugin } from "vite";
import { PLACEHOLDER_MAP } from "../shared/urls";

function replaceOutsideCodeFence(
  markdown: string,
  replacer: (line: string) => string,
): string {
  const lines = markdown.split("\n");
  const result: string[] = [];
  let inFence = false;
  let fenceChar = "";

  for (const line of lines) {
    const fenceMatch = line.match(/^(\s*)(`{3,}|~{3,})/);
    if (fenceMatch) {
      const currentFenceChar = fenceMatch[2][0];
      if (!inFence) {
        inFence = true;
        fenceChar = currentFenceChar;
      } else if (currentFenceChar === fenceChar) {
        inFence = false;
        fenceChar = "";
      }
      result.push(line);
      continue;
    }

    result.push(inFence ? line : replacer(line));
  }

  return result.join("\n");
}

function replacePlaceholders(src: string): string {
  return replaceOutsideCodeFence(src, (line) => {
    let result = line;
    for (const [placeholder, url] of Object.entries(PLACEHOLDER_MAP)) {
      result = result.replaceAll(placeholder, url);
    }
    return result;
  });
}

export function markdownUrlReplacePlugin(): Plugin {
  return {
    name: "markdown-url-replace",
    enforce: "pre",
    transform(code: string, id: string) {
      if (!id.endsWith(".md") || !code.includes("{{URL_")) return null;
      const transformed = replacePlaceholders(code);
      if (transformed === code) return null;
      return { code: transformed, map: null };
    },
  };
}
