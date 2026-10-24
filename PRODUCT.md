# NexwaCLI

<!-- impeccable:product-schema 1 -->

## Platform

Terminal application for Windows, macOS and Linux. This is a CLI/TUI, with no web frontend.

## Stack

Delegated by the founder. Python 3.11+, standard library at runtime. Optional PyInstaller builds for standalone distribution.

## Users and purpose

Nexwa customers use their own customer API keys to browse services, fund their wallet on the website, purchase boosts and track API orders. Developers can fork the MIT-licensed client and use its commands in scripts.

## Capabilities and constraints

Only the Nexwa public API at https://nexwa.store/api/v2 is used. Catalog prices and final charges come from Nexwa. Supported actions are services, balance, add, status and refill. Account verification, key management and wallet funding take place on nexwa.store.

The dashboard defaults to English and offers the website's English, Italian, French, German, Spanish and Russian languages in Settings. Machine-readable JSON keys and command names stay stable in English. Service content and API error messages remain as returned by Nexwa.

Order receipts are local to the computer and isolated by API key. They are not a complete account-wide order history. Delivery status must come from a live status request. Interrupted purchases retain their original request keys.

## Brand commitments

Nexwa name and website colors. A practical customer dashboard and boost panel with direct, concise copy. No unrelated integration names or credentials belong in the repository.

## Operating decisions

The founder requested implementation immediately and delegated the programming language. The founder confirmed that wallet balance and new orders take priority on the starting dashboard. English is the explicitly requested initial interface language.
