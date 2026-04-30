# Pair — Board Builder Launch Post (hand-drafted)

**Drafted:** 2026-04-22
**Status:** Draft — ready to publish when Pair IG/FB accounts are connected
**Why hand-drafted:** CMO Agent auto-generator produced an off-brand Spirit Library whiskey "proof" post instead of a Board Builder announcement. Queued bad post was removed from `posts/queue.json`. Regenerate later with a more explicit `idea` parameter once content_generator supports `--prompt` overrides.

---

## Instagram — Launch Announcement

### Image direction
Overhead flat-lay of a finished cheese board on warm oak with natural linen napkin. Three cheeses (one soft + bloomy, one aged hard, one blue), two pours of wine (a rosé and a light red) in simple stemless glasses, a small dish of dark chocolate squares, a small dish of marcona almonds. Late golden-hour light. Matte — no food-photography gloss. Phone frame showing the Pair app "Build a board for me" screen subtly visible in the corner.

### Caption (IG, 2,200-char limit — this is ~940)

Stop googling "cheese board ideas" at 4pm before a 7pm dinner party.

We built a Board Builder into Pair. Tell it the occasion (Date Night · Dinner Party · Picnic · Holiday · Casual · Tasting Flight) and how many guests. In three taps it picks a balanced board — soft + semi-hard + hard cheese, two wines that actually match your cheeses, a chocolate, a nut — with a per-person quantity estimate so you don't over- or under-buy.

Don't like a pick? Tap it. Swap it. The wine re-matches automatically.

Because the best hosts don't improvise. They *plan*, fast.

✨ New in Pair — available on TestFlight now.

Save this post for your next dinner party.

### Hashtag pool (use ~15, mix core + specifics)

#PairApp #BoardBuilder #CheeseBoard #CheeseAndWine #HostingTips #WineAndCheese #Charcuterie #WineLover #CheeseLover #CheesePlate #DinnerParty #DateNightAtHome #CheeseBoardInspo #CharcuterieBoard #HomeEntertaining

### Alt text (accessibility)

Overhead photo of a wooden cheese and wine pairing board, with three wedges of cheese, two glasses of wine, a small dish of dark chocolate, and almonds, arranged on a natural linen napkin in warm golden light.

---

## Facebook — same as IG caption, slightly longer tail

Append after the existing caption:

> Board Builder is part of Pair — the app that plans your cheese, wine, chocolate, and nut boards in under a minute. 84 cheeses, 73 wines, 41 chocolates, 18 nuts, all with pairing relationships worked out by actual sommeliers. Free on iOS.

---

## TikTok — 15-second hook script

**[0–2s]** Phone-in-hand POV, wide shot of an empty cutting board. Text overlay: "The 4pm host spiral."
**[2–5s]** Cut to stressed googling montage: "easy cheese board" / "how much cheese per person" / "what wine with brie." Text overlay: "Every. Single. Time."
**[5–8s]** Cut to hand opening Pair, tapping "Build a board for me," selecting "Date Night," stepper to "2 guests."
**[8–12s]** Cut to the suggested board filling in. Quick swap: tap a cheese, pick a different one, wine re-matches on screen.
**[12–15s]** Cut to the finished real board on the table, glasses poured. Text overlay: "Three taps. Done."
**Audio:** trending upbeat hosting / wine sound at the time of upload.

---

## Platform-specific posting notes
- **IG**: post first (9am or 7pm slot). Save to "Features" highlight after 24h.
- **FB**: same caption, re-crop image to 1.91:1 instead of 4:5 to avoid auto-pad.
- **TikTok**: upload vertical 9:16, screenrecord the Pair flow in-app for authenticity.

---

## To-do before publishing
- [ ] Add IG account ID to `brands/pair/config.json` (`instagram_account_id`)
- [ ] Add FB page ID (`facebook_page_id`)
- [ ] Generate final hero image via Imagen 4 Ultra from the image-direction prompt above
- [ ] Decide App Store link (once Pair hits App Store): add to `app_store_link`
- [ ] Decide primary website URL: add to `website`
- [ ] Drop into CMO queue manually, or re-run `main.py generate pair --platform instagram` with a constraining prompt once generator supports it
