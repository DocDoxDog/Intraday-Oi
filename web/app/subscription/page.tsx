import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";

export default function SubscriptionPage() {
  return (
    <TerminalLayout title="Subscription">
      <EmptyTerminalState title="Billing disabled" detail="Payment provider integration remains disabled until commercial eligibility, tax, refund and regulatory review is complete." />
    </TerminalLayout>
  );
}
