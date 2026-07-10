import Link from "next/link";

export default function HomePage() {
  return <main className="landing"><p className="eyebrow">AI Frontend Migration Factory</p><h1>Control Tower</h1><p>Review backend-owned migration state and prepare a mock run.</p><Link className="button" href="/migrations/new">Create mock migration</Link></main>;
}