import { EmptyState, LinkButton } from "../components/ui";

export default function NotFound({ inApp, message }: { inApp?: boolean; message?: string }) {
  return (
    <div className={inApp ? "" : "grid min-h-screen place-items-center bg-cream"}>
      <EmptyState
        icon="Map"
        title={message ?? "This page doesn't exist"}
        body="Check the address, or go back to your overview."
        action={<LinkButton to="/app" variant="primary">Go to overview</LinkButton>}
      />
    </div>
  );
}
