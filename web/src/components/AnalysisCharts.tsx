import { Area, AreaChart, Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SessionAsset } from "../types";

export default function AnalysisCharts({ asset, accent }: { asset: SessionAsset; accent: string }) {
  const series = [
    { title: "Energy over time", values: asset.audio?.energy_series ?? [] },
    { title: "Brightness over time", values: asset.audio?.spectral_centroid_series ?? [] },
  ];
  const pitches = Object.entries(asset.midi?.pitch_distribution ?? {}).map(([pitch, count]) => ({ pitch, count }));
  return <div className="space-y-4">
    {series.filter(s => s.values.length).map(series => <div key={series.title}>
      <h3 className="mb-2 text-sm text-muted-foreground">{series.title}</h3>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={series.values.map((value, index) => ({ index, value }))}>
          <XAxis dataKey="index" hide /><YAxis hide /><Tooltip />
          <Area dataKey="value" type="monotone" stroke={accent} fill={accent} fillOpacity={0.12} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>)}
    {pitches.length > 0 && <div><h3 className="text-sm text-muted-foreground">MIDI pitch distribution</h3>
      <ResponsiveContainer width="100%" height={160}><BarChart data={pitches}>
        <XAxis dataKey="pitch" /><YAxis /><Tooltip /><Bar dataKey="count" fill={accent} isAnimationActive={false} />
      </BarChart></ResponsiveContainer>
    </div>}
  </div>;
}
