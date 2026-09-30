# REGULATORY RESEARCH

Status: LEGAL_REVIEW_REQUIRED

Scope: Thailand first; then US, EU/UK and Singapore.

## Thailand

The Thai SEC currently publishes licensed investment advisory and derivatives advisory businesses.
On 17 September 2026 the SEC announced a public consultation on proposed amendments concerning
investment advice delivered through media, including online channels, intended to clarify when
media-based advice does or does not constitute investment-advisory/derivatives-advisory business.

This is especially relevant because the proposed product sends paid market analysis and
scenario planning through Telegram and a web terminal.

Operating posture:
- do not market as a broker
- do not accept customer funds
- do not accept or route orders
- avoid personalized recommendations
- avoid guaranteed outcomes
- keep a documented distinction between observed data, derived analytics and conditional scenarios
- obtain Thai legal review before paid public launch

## United States

The SEC describes an investment adviser broadly as a compensated person engaged in advising others
about securities or issuing analyses/reports concerning securities, subject to exclusions/exemptions.
The CFTC defines a Commodity Trading Advisor broadly to include compensated advice or analyses/reports
concerning commodity futures/options and related interests. The CFTC has historically recognized
specific exclusions/exemptions for certain standardized publication activity, but those boundaries
must be reviewed against the actual product.

Operating posture:
- do not assume the publisher/newsletter model automatically covers paid commodity-analysis subscriptions
- perform product-specific CFTC/SEC analysis where relevant
- geofence or restrict jurisdictions/features when counsel requires it

## UK

The FCA states that financial promotions can include websites, emails and social-media posts and
must be fair, clear and not misleading. Section 21 FSMA can restrict unauthorized financial promotions.

Operating posture:
- marketing copy and Telegram alerts must be treated as potential financial promotion
- use legal review for UK-facing promotion and product availability

## EU

ESMA has applied product-intervention measures to CFDs for retail clients, including leverage limits
and standardized protections. Product distribution and promotion should therefore be reviewed before
targeting EU retail CFD customers.

## Singapore

MAS requires a Capital Markets Services licence for specified regulated activities, including dealing
in capital-markets products and certain derivatives activities; exemptions can apply depending on the
business model.

Operating posture:
- determine whether paid market analysis/scenario services constitute a regulated activity
- obtain Singapore counsel before active solicitation of Singapore retail customers

## Product compliance architecture

REGULATORY_PROFILE
→ jurisdiction
→ customer_type
→ product_features
→ prohibited_features
→ required_disclosures
→ legal_review_status
→ effective_from
→ effective_to

The application must be able to disable customer-facing features by jurisdiction without changing
the underlying quant engine.

This document is not legal advice and all statuses remain LEGAL_REVIEW_REQUIRED unless counsel confirms.
