import { Link } from "react-router-dom";
import { Compass } from "lucide-react";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-4 text-center">
      <Compass className="mb-4 h-12 w-12 text-zinc-700" />
      <h1 className="text-3xl font-bold text-zinc-100">404</h1>
      <p className="mt-2 text-sm text-zinc-500">This page does not exist.</p>
      <Link to="/" className="btn-primary mt-6">
        Back to Dashboard
      </Link>
    </div>
  );
}
