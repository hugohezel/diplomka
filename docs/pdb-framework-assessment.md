# PDB a prenositeľnosť evaluačného frameworku M1–M9

Preskúmané 2. októbra 2026. Implementácia používa RCSB PDB Data API a aktuálne
verejné metadáta na úrovni jednej štruktúry (`entry`).

## Záver posúdenia

Framework sa na PDB dobre prenáša ako hodnotenie doložených metadát: zachováva
identifikátory, názov, autorstvo, kľúčové slová, riadenú klasifikáciu a životný
cyklus záznamu. Jeho celkové skóre však nemožno interpretovať ako univerzálnu
kvalitu repozitára ani ako vedeckú spoľahlivosť proteínovej štruktúry.

Oba preskúmané záznamy dosiahli **9/12 bodov**. Dva body zostávajú nedoložené,
pretože adaptér nemá ekvivalent všeobecného opisu a typu zdroja; tretí bod
predstavuje sémantickú informatívnosť názvu, ktorú framework nevyhodnocuje ani
pri ostatných repozitároch. Tento výsledok je vlastnosťou dostupných dôkazov a
zvoleného mapovania. Nevypovedá o chybnosti molekulového modelu.

## Čím sa špecializovaný repozitár líši

Zenodo prijíma rozličné výskumné výstupy a má všeobecný záznam s názvom, opisom
a deklarovaným typom. PDB organizuje štruktúrne dáta hierarchicky: záznam,
chemicky odlišné entity, konkrétne reťazce a biologické zostavy. Jedna štruktúra
môže obsahovať viac proteínov, nukleové kyseliny, ligandy a ďalšie komponenty.
Tieto úrovne majú samostatné metadáta a identifikátory.
[RCSB Data API](https://data.rcsb.org/)

Identifikátor PDB označuje štruktúrny záznam. Nemožno ho zamieňať za univerzálny
identifikátor proteínu: napríklad odkaz na UniProt patrí k molekulovej entite.
Rovnako treba oddeliť DOI štruktúry, DOI primárneho článku a DOI súvisiacich dát
v inom archíve. wwPDB ich pri 4HHB uvádza samostatne.
[Identifikátory PDB](https://www.rcsb.org/docs/general-help/identifiers-in-pdb),
[záznam 4HHB](https://www.wwpdb.org/pdb?id=pdb_00004hhb)

PDB používa PDBx/mmCIF dátový slovník a proces OneDep s validáciou a biokuráciou.
To umožňuje podrobnejšie doménové overovanie než všeobecná prítomnosť polí,
napríklad súlad modelu s experimentálnymi dátami či geometriu molekuly. Rôzne
experimentálne metódy potrebujú rôzne kritériá; NMR nemá univerzálny ekvivalent
röntgenového rozlíšenia.
[OneDep](https://www.wwpdb.org/deposition/faq),
[hodnotenie štruktúrnej kvality](https://www.rcsb.org/docs/general-help/assessing-the-quality-of-3d-structures)

## Mapovanie M1–M9

PDB nemožno označiť ako repozitár bez možnosti opisných metadát. Slovník obsahuje
napríklad voliteľné pole `struct.pdbx_model_details` pre textový opis metodiky,
ktorou model vznikol. OneDep umožňuje upravovať aj nepovinné položky a zbiera
podrobnosti o experimentálnych postupoch. Ide o špecializované opisy; ich
existencia neznamená, že automaticky spĺňajú všeobecný opis datasetu v M3.
[Opis metodiky modelu](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_struct.pdbx_model_details.html),
[návod OneDep](https://www.wwpdb.org/deposition/tutorial)

Preto nepridávame repository-level `FAIL` s tvrdením, že opisné metadáta nemožno
pridať. Súčasný výsledok M3 `UNSURE` opisuje chýbajúce všeobecné mapovanie v
adaptéri, nie preukázané obmedzenie depozičného rozhrania.

| Skupina | Dôkaz v PDB | Posúdenie prenositeľnosti |
| --- | --- | --- |
| M1 identifikátory | `rcsb_id`; DOI z riadku `database_2` označeného `PDB` | Dobre prenositeľné. Miestna syntax musí podporovať alfanumerické aj rozšírené PDB ID. Revízne číslo nenahrádza identifikátor nemennej verzie. |
| M2 názov | `struct.title` | Priame mapovanie. Informatívnosť stále vyžaduje sémantické posúdenie, ktoré súčasná implementácia nevykonáva. |
| M3 opis | Bez zvoleného ekvivalentu všeobecného opisu | Čiastočný súlad. `UNSURE`, bez bodu. Názov článku ani stručné poznámky o výbere modelu nevkladáme ako abstrakt. |
| M4 kľúčové slová | `struct_keywords.text` | Priame mapovanie po rozdelení textu na termíny podľa čiarok. Pôvodný text sa zachováva. |
| M5 riadené predmety | `struct_keywords.pdbx_keywords` | Dobre prenositeľné cez oficiálny depozičný slovník PDBx/mmCIF. Zložené klasifikácie sa rozdelia na komponenty; historické nerozpoznané termíny zostanú `UNSURE`. |
| M6 tvorcovia | `audit_author[].name`, `audit_author[].pdbx_ORCID` | Dobre prenositeľné autorstvo záznamu. Autori článku sú odlišná rola. Verejné ORCID a štruktúrované afiliácie nie sú zabezpečené pre každého autora. |
| M7 organizácie | `pdbx_database_status.process_site` | Čiastočný súlad: skutočný kód spracovateľskej organizácie je dôkaz pôvodu záznamu, nie afiliácie autora. ROR sa z neho neodvodzuje. |
| M8 typ zdroja | Bez všeobecného typu vo vybranom mapovaní | Čiastočný súlad. `UNSURE`, bez bodu. Experimentálna metóda a formát mmCIF majú iný význam než všeobecný typ `Dataset`. |
| M9 dátumy | `rcsb_accession_info.deposit_date`, `initial_release_date`, `revision_date` | Priame mapovanie životného cyklu záznamu. Depozícia nie je dátum experimentu a dátum článku nenahrádza verejné vydanie štruktúry. |

Slovník výslovne rozlišuje požiadavky na depozíciu od polí výsledného záznamu.
Napríklad názov aj kľúčové slová sú požadované pri depozícii. Prítomnosť poľa v
API sama osebe nedokazuje, že ho vedec musí ručne vyplniť.
[Názov](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_struct.title.html),
[kľúčové slová](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_struct_keywords.text.html),
[riadená klasifikácia](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_struct_keywords.pdbx_keywords.html)

## Overenie na živých záznamoch

Nasledujúce výsledky pochádzajú z celého adaptéra vrátane resolverov a agregátorov
spusteného 2. októbra 2026. Ide o dve prípadové štúdie, nie reprezentatívnu vzorku
všetkých PDB záznamov. Dohľadateľnosť v agregátoroch sa môže meniť.

| Záznam | Metóda | Skóre | Bonus | Resolver PDB ID / DOI | OpenAIRE | OpenAlex |
| --- | --- | --- | --- | --- | --- | --- |
| [4HHB](https://www.wwpdb.org/pdb?id=pdb_00004hhb) | X-RAY DIFFRACTION | 9/12 | 1/4,5 | PASS / PASS | PASS | PASS |
| [2N5E](https://www.wwpdb.org/pdb?id=pdb_00002n5e) | SOLUTION NMR | 9/12 | 1/4,5 | PASS / PASS | FAIL | FAIL |

Bonusový bod vzniká úspešným overením resolvera identifikátora záznamu a DOI
štruktúry. Chýbajú bonusy za ORCID a afiliácie každého autora a za identifikátor
konkrétnej verzie. Vyhľadávanie agregátorov nemení bodové skóre M1–M9.

Pri 4HHB sú v zázname dvaja tvorcovia štruktúry, zatiaľ čo primárny článok má
štyroch autorov. Pri 2N5E pole `database_2` obsahuje PDB aj BMRB DOI. Tieto
konkrétne prípady overujú, že adaptér nepreberá nesprávne autorstvo ani prvé
dostupné DOI.
[API 4HHB](https://data.rcsb.org/rest/v1/core/entry/4HHB),
[API 2N5E](https://data.rcsb.org/rest/v1/core/entry/2N5E)

Nenájdenie DOI 2N5E v dvoch agregátoroch znamená iba negatívny výsledok týchto
konkrétnych vyhľadávaní. PDB ID aj DOI sú funkčné a záznam je dostupný v doménovom
archíve. Framework preto potrebuje interpretovať všeobecnú agregáciu oddelene
od doménovej dohľadateľnosti.

## Dôsledky pre návrh frameworku

1. Zachovať M1–M9 ako spoločnú vrstvu a pri porovnávaní uvádzať aj pokrytie
   mapovania. Chýbajúci dôkaz vo vybranom API a preukázateľne chýbajúca hodnota
   v mapovanom poli sú odlišné situácie.
2. Doménovú validáciu zaradiť do samostatnej vrstvy: súlad sekvencií a reťazcov,
   identifikátory UniProt a taxónov, biologické zostavy, experimentálne dáta a
   wwPDB validačné ukazovatele podľa metódy. Táto verzia adaptéra ich nehodnotí.
3. Pri dohľadateľnosti rozlíšiť všeobecné agregátory a doménové indexy. Nález
   článku sa nesmie započítať ako nález samotného štruktúrneho datasetu.
4. Verzie hodnotiť podľa ich dostupného archívneho zdroja. PDB mení major/minor
   revíziu pri zachovaní prístupového kódu; aktuálny `entry` endpoint nepredstavuje
   historickú nemennú verziu.
   [Verzionovaný archív](https://www.wwpdb.org/ftp/pdb-versioned-ftp-site)

Implementácia nemení váhy ani menovateľ skóre. Nezavádza automatický `Dataset`,
fiktívne afiliácie ani odvodený identifikátor verzie. Vysvetlenia `UNSURE` a
diagnostika rozsahu sprístupňujú limity priamo vo výsledku aplikácie.

## Implementačný rozsah a reprodukovateľnosť

Adaptér je v `src/adapters/pdb_adapter.py`. Parsovanie prístupových kódov zdieľa
`pdb_identifiers.py`, klasifikácia používa datovaný lokálny slovník
`pdb_vocabulary.py`. Existujúci evaluátor dostáva natívne identifikačné ciele a
spoločný klient výslovný selektor DOI štruktúry. Pôvodný JSON sa nemení.

Katalóg obsahuje 16 polí s oddelenými a ozdrojovanými politikami depozície.
Pôvodné adaptéry a skórovanie používajú rovnaký spoločný evaluátor. Nie sú
potrebné nové knižnice. Rozšírené identifikátory podporujeme syntakticky;
existenciu budúcich ID nepotvrdzujú testy so syntetickými príkladmi.

Testy zahŕňajú dva archivované API záznamy, rozpoznávanie vstupov, hranice URL,
výber DOI podľa databázy, autorstvo, ORCID, slovník, chronológiu, revízie,
neúplné odpovede, zachovanie JSON a integráciu do aplikácie. Celá sada má
75 úspešných testov; samostatné živé overenie potvrdilo komunikáciu s PDB,
DOI resolverom a oboma agregátormi.
