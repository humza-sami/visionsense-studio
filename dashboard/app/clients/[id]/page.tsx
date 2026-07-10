import { notFound } from "next/navigation";

import { VERTICAL_SKINS } from "@/components/verticals";
import { getClient } from "@/lib/data/clients";

export default async function ClientOverviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const client = getClient(id);
  if (!client) notFound();
  const Skin = VERTICAL_SKINS[client.vertical];
  return <Skin client={client} />;
}
