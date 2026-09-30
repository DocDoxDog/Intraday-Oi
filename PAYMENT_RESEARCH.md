# PAYMENT RESEARCH

Status: COMMERCIAL DECISION PENDING

## Current evidence

Stripe lists Thailand among supported countries/regions. Stripe's Thailand PromptPay page currently states PromptPay does not support recurring payments. Stripe also classifies financial products/services as restricted and may require additional review/approval depending on business classification.

Paddle supports Thailand and operates as Merchant of Record for supported software/digital products, including tax handling. However Paddle's Acceptable Use Policy explicitly excludes investment/financial advice, trading signals and strategies, and trading platforms. That makes Paddle unsuitable unless the product is re-scoped and Paddle confirms eligibility in writing.

Lemon Squeezy lists Thailand as a supported country for bank payouts/purchases.

Xendit offers Thailand subscription billing with recurring cards, direct debit and local payment methods.

Telegram's current Bot Payments documentation says digital goods/services sold inside Telegram apps must use Telegram Stars; web/Telegram Mini Apps can also use third-party payment flows subject to the current platform/payment rules. Telegram itself does not process ordinary provider payments.

## Comparison

| Provider | Thailand | Recurring | MoR | Key concern |
|---|---|---:|---:|---|
| Stripe | YES | Card/Billing supported; PromptPay itself says NO recurring | NO | Financial-services classification requires review |
| Paddle | Seller support YES | YES | YES | Explicitly excludes investment/financial advice and trading signals |
| Lemon Squeezy | YES | YES | YES/MoR model | Verify financial-content eligibility before adoption |
| Xendit | YES | YES | NO | Strong Thai recurring/local rails; merchant handles own tax/compliance |
| Telegram Stars | YES inside Telegram | YES | N/A | Digital goods/services in Telegram use Stars; economics/platform constraints |

## Decision framework

Primary web billing candidate:
Stripe, subject to written business-classification approval.

Thai-local recurring candidate:
Xendit, subject to pricing, merchant-account and tax/compliance review.

MoR candidates:
Paddle is currently blocked by its published AUP for investment/financial advice/trading signals; Lemon Squeezy requires explicit eligibility confirmation.

Telegram:
Use external web checkout for the main subscription journey during legal/payment review. Do not bypass Telegram platform rules for digital goods/services. Keep Telegram focused on delivery and account linkage.

No production payment integration until:
- company/entity details are verified
- product classification is approved by the provider
- refund/chargeback flow is tested
- webhook signature verification is implemented
- subscription state is mirrored into entitlements
- terms/privacy/refund pages are live
