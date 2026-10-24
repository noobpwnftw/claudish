# Onboarding poll, 2026-10-24 (synthetic)

Not real users: the five personas of the [2026-10-23 poll](2026-10-23-persona-poll.md), each an
agent reading the repository, the homepage and the install guide read-only, and running `claudish
init` and `claudish templates` in a scratch folder. The brief was the owner's funnel: a slop
keyboard on day 1, the polish on day 2, the reveal on day 3 (the words cd_AI says to a model are a
file you can change). Since the last poll: compose by default, no model ships (Claude with your
own key, or `setup --profile local` with Gemma 4 E4B), named voices, the templates as data.

| Persona | Keeps it after 30 days | Shares it |
| --- | --- | --- |
| Everyday Mac writer | 2/10 (6/10 as a normal Mac app with proofread one click away) | 7/10 |
| Power-user developer | 6/10 | 7/10 (the slop), 4/10 (the agent part) |
| Chinese pinyin user | 6/10 with proofread, 2/10 on the slop default | 5/10 |
| Tech critic | still used 3/10 | spreads 7/10 |
| Privacy-minded SRE | 6/10 (home, local) | recommends 4/10 |

## Where they agreed

- **The slop lands and spreads** (7/10 from three of five): "can't make it tonight" turned into
  "my current bandwidth is fully allocated" and the five voices on one sentence are the
  screenshots. It is a day-1 hook, not a reason to stay.
- **Proofread is what people would keep** (the Mac writer, the pinyin user): the slop is for
  sharing, not for sending, and a second-language writer cannot always tell when it is over the
  top. Two asked for the voice to be a first-run choice and to be visible in the panel.
- **The install is still the wall** for everyone but the developer: a terminal, a venv, a key, an
  unsigned app, logging out twice. A real Mac app with a first-run window (G37) is what the
  everyday writer would need.
- **Day 3 needs a door:** the reveal lives in the README and a JSON file; the writer asked for a
  voice menu in the input menu (G52), the developer for hot reload and a one-line way to try a
  voice, the critic for the templates excerpt on the homepage.

## Found and fixed the same day

- The homepage said cd_AI "looks at the screen only when you press F8"; at a terminal prompt, a
  compose request also sends the terminal's last lines (to a hosted model, by default now). The
  claim is corrected, and the usage guide says where the lines go and that redaction is a best
  effort.
- "Good slop needs a frontier model" contradicted the benchmark (local Gemma 4 E4B ahead of
  Haiku); the docs now say the Claude default is there because it runs on any computer.
- `pip install --user` fails on current Ubuntu, Debian and Homebrew Pythons; the install is a
  venv in the checkout.
- Stale lines: "local inference remains the default"; agent questions answered with "1" and "2"
  although choices are not numbered.

## For the owner

- **Enter** (the pinyin user, whose view weighs most on keys): in every CJK input method Enter
  commits the raw letters; here it sends an instruction, and Shift+Enter (keep your words) is
  Slack's newline. G47 already makes the summon key a setting; the poll asks for Enter to commit
  by default.
- **The terminal screen and a hosted model** (the SRE): `read_terminal` is on by default, so with
  the Claude default a compose request at a terminal sends its last lines to Anthropic. Off by
  default for hosted profiles, or asked once per app?
- **The voice for work:** a first-run question in setup ("slop for fun, proofread for work") and
  the voice named in the panel's footer.
- **The owner's answers:** the terminal's last lines stay on with any model (documented): whoever
  uses a hosted model with their own key has chosen to trust that provider (a slop keyboard's
  audience cares less about privacy, and anyone who does should not use a hosted key), and what a
  terminal shows is mostly compile errors, not secrets. Enter
  keeps summoning (G47 stays the way to change it); setup asks for a voice on its first
  interactive run (done), and the panel does not name the voice: you chose it, and being told
  water is wet at every keystroke is noise. The CJK Enter habit is a later setting (G47), and
  swapping moves every Enter action with it.
- Smaller asks: a share card in the demo (before and after, for Slack or X); a SECURITY.md (what
  leaves the machine per profile and mode); `"tone"` directly on a binding; hot reload of the
  config and templates; fcitx5 on Linux (the pinyin user's Rime runs there, and IBus-only is not
  stated); safer key advice (a 0600 environment file for the unit; no key in shell history).
