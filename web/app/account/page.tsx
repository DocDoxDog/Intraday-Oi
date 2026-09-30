import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";

export default function AccountPage() {
  return (
    <TerminalLayout title="Account">
      <EmptyTerminalState title="Customer authentication pending" detail="Account access will be enabled after Supabase Auth, tenant provisioning and entitlement verification are connected." />
    </TerminalLayout>
  );
}
