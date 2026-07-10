export type ClientAudioTags = {
  fileName: string;
  codec?: string;
  bitrate?: number;
  sampleRate?: number;
  duration?: number;
  title?: string;
  artist?: string;
  album?: string;
};

export async function readClientAudioTags(files: FileList | null): Promise<ClientAudioTags[]> {
  if (!files) return [];
  const { parseBlob } = await import("music-metadata");
  const results: ClientAudioTags[] = [];
  for (const file of Array.from(files)) {
    if (!file.type.startsWith("audio/")) continue;
    try {
      const metadata = await parseBlob(file);
      results.push({
        fileName: file.name,
        codec: metadata.format.codec,
        bitrate: metadata.format.bitrate,
        sampleRate: metadata.format.sampleRate,
        duration: metadata.format.duration,
        title: metadata.common.title,
        artist: metadata.common.artist,
        album: metadata.common.album
      });
    } catch {
      results.push({ fileName: file.name });
    }
  }
  return results;
}
