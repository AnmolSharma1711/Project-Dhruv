import asyncio
import json
import re
import time
import unicodedata
import httpx

from .navigation import POINTS, request


def words(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(" " if unicodedata.category(c).startswith("P") else c for c in text).split())


class Guide:
    def __init__(self, providers, camera, data, nav=request):
        self.providers = providers
        self.camera = camera
        self.nav = nav
        self.catalog = json.loads((data / "locations.json").read_text(encoding="utf8"))
        if set(self.catalog) != POINTS:
            raise ValueError("locations.json must contain the eight SLAM checkpoints")
        self.aliases = {}
        for key, record in self.catalog.items():
            if not isinstance(record["facts"], str) or not isinstance(record["aliases"], list):
                raise ValueError("Invalid exhibit record")
            for alias in [key, *record["aliases"]]:
                alias = words(alias)
                if not alias or self.aliases.setdefault(alias, key) != key:
                    raise ValueError("Empty or ambiguous checkpoint alias")
        self.pending = None
        self.proposed = None
        self.hindi = providers.language.startswith("hi")

    def say(self, english, hindi):
        return hindi if self.hindi else english

    async def reply(self, history, cues=()):
        text = words(history[-1]["content"])
        for cue in cues:
            text = words(cue.sub("", text))
        text = re.sub(r"^(?:(?:hey|hello|हेलो) )?(?:dhruv|ध्रुव)\s+", "", text)
        state = await self.nav("status")
        if state["mode"] in {"uncertain", "moving"}:
            raise RuntimeError("Navigation owns robot")
        pending, self.pending, self.proposed = self.pending, None, None
        if pending and text in {"yes", "yes please", "confirm", "go ahead", "हाँ", "हां", "जी हाँ", "चलो"}:
            target, revision, deadline = pending
            if time.monotonic() <= deadline and revision == state["revision"]:
                # Persist intent on the host before returning. The supervisor immediately suspends voice.
                await self.nav("go", point=target, revision=revision)
                return None
            return self.say("That request expired. Please ask again.", "कृपया फिर से जगह बताइए।")
        if pending and text in {"no", "cancel", "नहीं", "रद्द"}:
            return self.say("Okay, staying here.", "ठीक है, हम यहीं रहेंगे।")
        english = re.fullmatch(r"(?:(?:could you|can you|please) )?(?:go to|navigate to|take me to|let s go to) (.+?)(?: please)?", text)
        hindi = re.fullmatch(r"(?:मुझे |चलो )?(.+?)(?: पर| पे| तक)? (?:ले चलो|ले चलिए|चलो|चलिए|जाओ|जाइए)", text)
        direction = english or hindi
        if direction or text == "take me there":
            phrase = direction[1] if direction else "there"
            target = self.aliases.get(phrase)
            if not target and not re.search(r"\b(?:and|or|then|except)\b| और | या ", phrase):
                resolved = await self.providers.destination(history, self.catalog)
                target = resolved if resolved in POINTS else None
            if not target:
                return self.say("Which checkpoint? Please say go to and its name.",
                                "कौन सा चेकपॉइंट? कृपया जगह का नाम बताइए।")
            if state["mode"] != "ready":
                return self.say("Please have the operator localize me first.", "पहले ऑपरेटर मेरी लोकेशन सेट करें।")
            if state["current"] == target:
                return self.say(f"We are already at {target}.", f"हम पहले से {target} पर हैं।")
            self.proposed = target, state["revision"]
            return self.say(f"Shall I take you to {target}?", f"क्या मैं आपको {target} तक ले चलूँ?")
        context = {"current_checkpoint": state["current"], "last_confirmed_arrival": state["last"],
                   "exhibits": self.catalog}
        # Azure chooses which observation is needed from the utterance and recent dialogue.
        # This decision has no access to the motion interface.
        kind = await self.providers.perception_needed(history)
        if kind in {"face", "scene"}:
            try:
                context["observation"] = await self.camera.observe(kind, history[-1]["content"])
            except (TimeoutError, OSError, ValueError, RuntimeError, httpx.HTTPError):
                context["observation"] = {"unavailable": True}
        return await self.providers.answer(history, context)

    def delivered(self):
        if self.proposed:
            self.pending = (*self.proposed, time.monotonic() + 45)
            self.proposed = None
