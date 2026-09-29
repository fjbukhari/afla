// Builds the three AFLA beginner decks (pptxgenjs). Screenshots come from real AFLA reports on public GIAB data.
const pptxgen = require('pptxgenjs');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const sharp = require('sharp');
const fa = require('react-icons/fa');
const fs = require('fs');

const C = {
  teal: '0B4F6C', tealDark: '083A50', mint: '20A39E', coral: 'E4572E', ink: '1B2A38', muted: '5B6B7A',
  light: 'EEF4F6', white: 'FFFFFF', line: 'D5E0E4', gold: 'C98A00', red: 'B42318', green: '1A7F37',
};
const HEAD = 'Cambria', BODY = 'Calibri';
const SHOTS = '/opt/shots/';
const OUT = process.argv[2] || '/home/user/afla/docs/slides/';

async function icon(name, color) {
  const Comp = fa[name];
  if (!Comp) throw new Error('icon ' + name);
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, {color: '#' + color, size: 256}));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return 'image/png;base64,' + buf.toString('base64');
}

class Deck {
  constructor(file, title) {
    this.file = file; this.pres = new pptxgen(); this.pres.layout = 'LAYOUT_WIDE';   // 13.33 x 7.5 in
    this.pres.author = 'AFLA project'; this.pres.title = title; this.n = 0;
  }
  footer(s, dark = false) {
    this.n += 1;
    s.addText(`AFLA  ·  education and research only  ·  ${this.n}`, {x: 0.5, y: 7.0, w: 8, h: 0.3, fontFace: BODY, fontSize: 10,
      color: dark ? 'A9C6D3' : C.muted, margin: 0, isTextBox: true});
  }
  async iconCircle(s, name, x, y, d, bg, fg = C.white) {
    s.addShape(this.pres.shapes.OVAL, {x, y, w: d, h: d, fill: {color: bg}, line: {color: bg}});
    const pad = d * 0.24;
    s.addImage({data: await icon(name, fg), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad});
  }
  title(s, text, sub) {
    s.addText(text, {x: 0.5, y: 0.35, w: 12.3, h: 0.8, fontFace: HEAD, fontSize: 34, bold: true, color: C.ink, margin: 0, isTextBox: true});
    if (sub) s.addText(sub, {x: 0.5, y: 1.1, w: 12.3, h: 0.45, fontFace: BODY, fontSize: 16, color: C.muted, italic: true, margin: 0, isTextBox: true});
  }
  async cover(kicker, title, sub, iconName) {
    const s = this.pres.addSlide(); s.background = {color: C.teal};
    await this.iconCircle(s, iconName, 0.8, 1.3, 1.3, C.coral);
    s.addText(kicker, {x: 0.8, y: 2.9, w: 11, h: 0.5, fontFace: BODY, fontSize: 18, color: 'A9D6E0', bold: true, charSpacing: 2, margin: 0, isTextBox: true});
    s.addText(title, {x: 0.8, y: 3.4, w: 11.5, h: 1.4, fontFace: HEAD, fontSize: 48, bold: true, color: C.white, margin: 0, isTextBox: true});
    s.addText(sub, {x: 0.8, y: 4.9, w: 11, h: 0.9, fontFace: BODY, fontSize: 20, color: 'DCEAF0', margin: 0, isTextBox: true});
    s.addText('Education and research use only · not for clinical diagnosis or patient management', {x: 0.8, y: 6.3, w: 11, h: 0.4,
      fontFace: BODY, fontSize: 13, color: 'F4B8A7', margin: 0, isTextBox: true});
    this.n += 1;
    return s;
  }
  content(bg = C.white) { const s = this.pres.addSlide(); s.background = {color: bg}; return s; }
  bullets(s, items, opt) {
    // one paragraph per item; the bullet sits on the first run, the line break on the last
    const runs = items.map((t, i) => {
      const last = i === items.length - 1;
      if (Array.isArray(t)) return [{text: t[0] + ' ', options: {bold: true, bullet: true}}, {text: t[1], options: {breakLine: !last}}];
      return [{text: t, options: {bullet: true, breakLine: !last}}];
    }).flat();
    s.addText(runs, {fontFace: BODY, fontSize: 16, color: C.ink, paraSpaceAfter: 8, valign: 'top', margin: 0.05, isTextBox: true, ...opt});
  }
  shot(s, file, x, y, w, caption) {
    const h = w * 1290 / 2100;
    s.addShape(this.pres.shapes.RECTANGLE, {x: x - 0.04, y: y - 0.04, w: w + 0.08, h: h + 0.08, fill: {color: C.line}, line: {color: C.line},
      shadow: {type: 'outer', blur: 6, offset: 2, angle: 90, color: '000000', opacity: 0.18}});
    s.addImage({path: SHOTS + file, x, y, w, h});
    if (caption) s.addText(caption, {x, y: y + h + 0.08, w, h: 0.3, fontFace: BODY, fontSize: 11, color: C.muted, italic: true, margin: 0, isTextBox: true});
    return h;
  }
  async cards(s, items, x, y, w, h, cols, bg = C.light) {
    const gap = 0.3, cw = (w - gap * (cols - 1)) / cols, rows = Math.ceil(items.length / cols), ch = (h - gap * (rows - 1)) / rows;
    for (let i = 0; i < items.length; i++) {
      const [ic, head, body, color] = items[i], cx = x + (i % cols) * (cw + gap), cy = y + Math.floor(i / cols) * (ch + gap);
      s.addShape(this.pres.shapes.ROUNDED_RECTANGLE, {x: cx, y: cy, w: cw, h: ch, fill: {color: bg}, line: {color: bg}, rectRadius: 0.12});
      await this.iconCircle(s, ic, cx + 0.2, cy + 0.2, 0.6, color || C.teal);
      s.addText(head, {x: cx + 0.95, y: cy + 0.2, w: cw - 1.1, h: 0.6, fontFace: HEAD, fontSize: 17, bold: true, color: C.ink, valign: 'middle', margin: 0, isTextBox: true});
      s.addText(body, {x: cx + 0.2, y: cy + 0.9, w: cw - 0.4, h: ch - 1.0, fontFace: BODY, fontSize: 16, color: C.ink, valign: 'top', margin: 0, isTextBox: true});
    }
  }
  steps(s, items, x, y, w) {    // numbered process flow, left to right
    const gap = 0.25, sw = (w - gap * (items.length - 1)) / items.length;
    items.forEach(([head, body], i) => {
      const sx = x + i * (sw + gap);
      s.addShape(this.pres.shapes.OVAL, {x: sx, y, w: 0.7, h: 0.7, fill: {color: i === items.length - 1 ? C.coral : C.teal}, line: {color: C.white}});
      s.addText(String(i + 1), {x: sx, y, w: 0.7, h: 0.7, fontFace: HEAD, fontSize: 22, bold: true, color: C.white, align: 'center', valign: 'middle', margin: 0, isTextBox: true});
      if (i < items.length - 1) s.addShape(this.pres.shapes.LINE, {x: sx + 0.8, y: y + 0.35, w: sw + gap - 0.9, h: 0, line: {color: C.line, width: 2, endArrowType: 'triangle'}});
      s.addText(head, {x: sx, y: y + 0.85, w: sw, h: 0.6, fontFace: HEAD, fontSize: 17, bold: true, color: C.ink, valign: 'top', margin: 0, isTextBox: true});
      s.addText(body, {x: sx, y: y + 1.55, w: sw, h: 2.9, fontFace: BODY, fontSize: 15.5, color: C.ink, valign: 'top', margin: 0, isTextBox: true});
    });
  }
  table(s, rows, x, y, w, colW, fontSize = 15, rowH = 0.5) {
    const data = rows.map((r, i) => r.map(c => ({text: c, options: {bold: i === 0, color: i === 0 ? C.white : C.ink,
      fill: {color: i === 0 ? C.teal : (i % 2 ? C.white : C.light)}}})));
    s.addTable(data, {x, y, w, colW, rowH, fontFace: BODY, fontSize, border: {type: 'solid', pt: 0.5, color: C.line}, margin: 0.06, valign: 'middle'});
  }
  stat(s, value, label, x, y, w, color = C.teal) {
    s.addText(value, {x, y, w, h: 0.95, fontFace: HEAD, fontSize: 44, bold: true, color, margin: 0, isTextBox: true});
    s.addText(label, {x, y: y + 0.95, w, h: 0.7, fontFace: BODY, fontSize: 13, color: C.muted, valign: 'top', margin: 0, isTextBox: true});
  }
  async closing(title, lines, iconName) {
    const s = this.pres.addSlide(); s.background = {color: C.teal};
    await this.iconCircle(s, iconName, 0.8, 1.0, 1.1, C.coral);
    s.addText(title, {x: 0.8, y: 2.3, w: 11.5, h: 0.9, fontFace: HEAD, fontSize: 40, bold: true, color: C.white, margin: 0, isTextBox: true});
    s.addText(lines.map((t, i) => ({text: t, options: {bullet: true, breakLine: i < lines.length - 1}})),
      {x: 0.8, y: 3.4, w: 11.5, h: 3.0, fontFace: BODY, fontSize: 18, color: 'E3EEF2', paraSpaceAfter: 10, valign: 'top', margin: 0, isTextBox: true});
    this.footer(s, true);
    return s;
  }
  async save() { await this.pres.writeFile({fileName: OUT + this.file}); console.log('wrote', this.file); }
}

// =====================================================================================================================
async function deck1() {
  const d = new Deck('AFLA_1_Getting_Started.pptx', 'AFLA 1: Getting started');
  let s = await d.cover('AFLA BEGINNER GUIDE 1 OF 3', 'Getting started with AFLA', 'Illumina and DNBSEQ panels and exomes in EPI2ME Desktop: install, set up, first run', 'FaPlay');
  s.addNotes('Welcome. This first deck gets everyone from an empty laptop to a first finished AFLA report. No Linux experience needed.');

  s = d.content(); d.title(s, 'What is AFLA?', 'The EPI2ME experience, for short-read sequencing');
  await d.cards(s, [
    ['FaWindowMaximize', 'Same app you know', 'EPI2ME Desktop runs Nanopore workflows. AFLA adds workflows for Illumina / DNBSEQ reads: pick files, click Run, read a report.'],
    ['FaDna', 'Germline and somatic', 'Inherited disease (single patients, trios) and tumours (tumour-only or tumour + normal). Panels and exomes.'],
    ['FaFileMedical', 'From any starting point', 'Raw FASTQ, aligned BAM/CRAM, or just a VCF from a provider, Galaxy, DRAGEN or Nanopore.', C.mint],
    ['FaGraduationCap', 'Built for teaching', 'Interactive report, ACMG/AMP evidence panel, exercise mode for students, printable case report.', C.coral],
  ], 0.5, 1.75, 12.3, 4.9, 2);
  d.footer(s);
  s.addNotes('Key idea: AFLA is not a new app. It is a set of workflows that EPI2ME Desktop runs, exactly like its own Nanopore workflows.');

  s = d.content(); d.title(s, 'How the pieces fit together', 'Four programs on one Windows laptop, and what they produce');
  d.steps(s, [
    ['EPI2ME Desktop', 'The window you click in: forms, progress, report viewer.'],
    ['Docker Desktop', 'Runs each tool (bwa, GATK, VEP...) in a sealed "container": no manual installs.'],
    ['WSL2 Ubuntu', 'A Linux inside Windows. Holds the AFLA code and the helper scripts.'],
    ['Resources folder', 'Reference genome and databases (ClinVar, gnomAD, REVEL...) in one folder.'],
    ['Your report', 'afla-report.html: opens in EPI2ME or any browser, even offline.'],
  ], 0.5, 2.0, 12.3);
  d.footer(s);

  s = d.content(); d.title(s, 'What you need', 'Tested on a 16-core, 64 GB laptop; runs on smaller machines');
  d.stat(s, '4+', 'CPU cores (16 is comfortable for exomes)', 0.5, 1.9, 2.8);
  d.stat(s, '12 GB', 'RAM minimum; 16 GB+ better. Detected automatically', 3.6, 1.9, 2.8);
  d.stat(s, '60 GB', 'free disk for resources (25 GB with the lean option), plus your data', 6.7, 1.9, 2.8, C.coral);
  d.stat(s, '0', 'cost: all tools free; some databases free for non-commercial use', 9.8, 1.9, 2.8, C.mint);
  d.bullets(s, [['Software:', 'Windows 10/11 (or macOS/Linux), EPI2ME Desktop, Docker Desktop, WSL2 Ubuntu.'],
    ['Optional:', 'an NVIDIA GPU (DeepVariant runs faster), Claude Code in Ubuntu as a helper.'],
    ['Internet:', 'only for installing and downloading databases; analysis runs offline.']], {x: 0.5, y: 4.2, w: 12.3, h: 2.4});
  d.footer(s);

  s = d.content(); d.title(s, 'Install in five steps', 'Full instructions: docs/INSTALL.md');
  d.steps(s, [
    ['WSL2 Ubuntu', 'PowerShell (admin):\nwsl --install -d Ubuntu\nThen set memory in C:\\Users\\you\\.wslconfig'],
    ['Docker', 'Install Docker Desktop. Tick "Use WSL 2 engine" and WSL integration for Ubuntu. Test: docker run hello-world'],
    ['EPI2ME', 'Install EPI2ME Desktop from the Nanopore website and open it once.'],
    ['AFLA code', 'In Ubuntu:\ngit clone ... afla.git\n(see INSTALL.md for the exact line)'],
    ['Resources', 'bash scripts/afla-setup.sh\nAsks before each big download.'],
  ], 0.5, 2.0, 12.3);
  s.addText('GPU users: install only the WINDOWS NVIDIA driver, never a Linux one inside Ubuntu. Check with scripts/afla-gpu-check.sh',
    {x: 0.5, y: 6.1, w: 12.3, h: 0.5, fontFace: BODY, fontSize: 14, color: C.red, bold: true, margin: 0, isTextBox: true});
  d.footer(s);

  s = d.content(); d.title(s, 'The resources folder', 'One command fills it; EPI2ME finds everything inside it');
  d.table(s, [['Folder', 'What is inside', 'Size'],
    ['reference/', 'GRCh38 genome (no-alt analysis set) + bwa index', '9 GB'],
    ['vep/', 'Ensembl VEP 115 cache (genes + gnomAD v4.1 frequencies), FASTA, plugins', '30 GB'],
    ['clinvar/', 'ClinVar variants + amino-acid index for ACMG PS1/PM5', '0.2 GB'],
    ['revel/, alphamissense/', 'Missense prediction scores (non-commercial licences)', '1.4 GB'],
    ['constraint/, hpo/, panelapp/', 'Gene tolerance, phenotype ontology, expert gene panels', '0.3 GB'],
    ['somatic/, civic/', 'Mutect2 germline resource + panel of normals; CIViC cancer evidence', '3.5 GB'],
  ], 0.5, 1.8, 8.0, [2.2, 4.8, 1.0], 14, 0.62);
  await d.iconCircle(s, 'FaFolderOpen', 9.4, 1.9, 1.2, C.mint);
  d.bullets(s, ['Re-run any time: files already there are kept.', 'ClinVar refreshes when older than 60 days.',
    'Copy the folder to other computers on a USB disk.', '--lean skips the 30 GB VEP cache.'], {x: 9.0, y: 3.4, w: 3.8, h: 3.2, fontSize: 14});
  d.footer(s);

  s = d.content(); d.title(s, 'Put AFLA into EPI2ME', 'Two ways');
  await d.cards(s, [
    ['FaLaptopCode', 'This laptop: install script', 'In Ubuntu run\nbash scripts/install-epi2me.sh\nRestart EPI2ME: "AFLA germline" and "AFLA somatic" appear. Re-run after every update (git pull).'],
    ['FaGithub', 'Any computer: import from GitHub', 'EPI2ME → Workflows → Import workflow → paste\ngithub.com/fjbukhari/afla\nYou get "AFLA germline"; its form has an Analysis mode switch for somatic.', C.coral],
  ], 0.5, 1.8, 12.3, 3.2, 2);
  d.bullets(s, ['Students\' computers: minimum 4 cores and 12 GB RAM; CPU and memory are detected automatically.',
    'No Docker available? Make the VCF on usegalaxy.eu, then start AFLA from the VCF.'], {x: 0.5, y: 5.3, w: 12.3, h: 1.4});
  d.footer(s);

  s = d.content(); d.title(s, 'Where does the analysis start?', 'Give ONE input; AFLA skips what is already done');
  await d.cards(s, [
    ['FaFileAlt', 'FASTQ folder', 'Raw reads (*_R1_001.fastq.gz + *_R2_001.fastq.gz). Everything runs: QC, alignment, calling, CNV, annotation, report.'],
    ['FaStream', 'BAM / CRAM', 'Reads already aligned to GRCh38. Alignment is skipped; coverage, calling, CNV and report run.', C.mint],
    ['FaListUl', 'VCF file', 'Variants from anywhere (provider, Galaxy, DRAGEN, Nanopore). Annotation, ACMG/tiers and report only.', C.coral],
  ], 0.5, 1.8, 12.3, 2.9, 3);
  d.bullets(s, [['Reference:', 'GRCh38 only. Set "Resources folder" and the rest is found for you.'],
    ['Target regions (BED):', 'the capture kit or panel file from the vendor. Needed for CNV and TMB.'],
    ['Folder names:', 'no spaces or "+"; files are read where they are, never copied.']], {x: 0.5, y: 5.0, w: 12.3, h: 1.8});
  d.footer(s);

  s = d.content(); d.title(s, 'Which library do you have?', 'Library chemistry decides two switches');
  d.table(s, [['Library type', 'Examples', 'What to set in the form'],
    ['Hybrid capture', 'SureSelect, Twist, IDT xGen, KAPA HyperCap', 'Defaults + kit BED'],
    ['Tagmentation', 'Illumina DNA Prep (with Enrichment), Nextera Flex', 'Defaults + BED'],
    ['Ligation', 'TruSeq, KAPA HyperPrep, MGI/BGI libraries', 'Defaults + BED'],
    ['Amplicon (PCR)', 'AmpliSeq, TruSight/TSCA, QIAseq, CleanPlex', 'Tick "Amplicon panel" + give the primer BED'],
    ['UMI libraries', 'QIAseq, xGen Prism, Twist UMI, Agilent XT HS', 'UMIs = inline (+ read structure) or read_name'],
  ], 0.5, 1.8, 12.3, [2.3, 5.0, 5.0], 15, 0.5);
  d.bullets(s, [['Why amplicon mode?', 'amplicon reads all start at the primers, so "duplicates" are real data, and primer bases must be clipped.'],
    ['Why UMIs?', 'reads from one original molecule are merged into one consensus read: errors vanish, 1-5% variants become believable.']],
    {x: 0.5, y: 5.2, w: 12.3, h: 1.6});
  d.footer(s);

  s = d.content(); d.title(s, 'Your first run (15 minutes)', 'Public practice data: the GIAB Ashkenazi trio, chromosome 20');
  d.steps(s, [
    ['Get data', 'bash scripts/afla-testdata.sh /mnt/c/Users/you/afla-testdata'],
    ['Open the form', 'EPI2ME → AFLA germline → Run'],
    ['Fill 5 fields', 'FASTQ folder, Sample sheet (trio.csv), Resources folder, Reference (chr20.fa), Target regions (chr20.targets.bed)'],
    ['Run', 'Watch the progress; it finishes in about 15 minutes.'],
    ['Open the report', 'EPI2ME Report tab, or afla-report.html in any browser.'],
  ], 0.5, 1.9, 12.3);
  d.footer(s);
  s.addNotes('Do this live with the class. While it runs, explain what each step does using the pipeline slide in deck 2.');

  s = d.content(); d.title(s, 'If something goes wrong');
  d.table(s, [['What you see', 'What to do'],
    ['"No paired FASTQ files found"', 'You chose the wrong folder: the message lists what is there. Pick the folder with the _R1/_R2 files.'],
    ['"... is an index file; using ..."', 'Fine: you picked a .fai/.tbi; the file next to it is used.'],
    ['"No bwa index found"', 'Use the reference from afla-setup.sh, or tick "Build bwa index" once (1 hour).'],
    ['Run stops: out of memory', 'Close other programs; raise memory in .wslconfig; or lower "Maximum memory".'],
    ['DeepVariant fails at once', 'GPU not visible to Docker: run afla-gpu-check.sh, or untick "Use the GPU".'],
    ['Disk filling up', 'Delete the "work" folder of finished runs.'],
    ['claude: command not found', 'sudo ln -sf ~/.local/bin/claude /usr/local/bin/claude'],
  ], 0.5, 1.5, 12.3, [4.2, 8.1], 15, 0.62);
  d.footer(s);

  s = d.content(); d.title(s, 'Words you will meet', 'A beginner\'s glossary');
  d.table(s, [['Term', 'Meaning'],
    ['FASTQ', 'Raw reads with quality scores, straight from the sequencer'],
    ['BAM / CRAM', 'Reads placed (aligned) on the reference genome; CRAM is the smaller format'],
    ['VCF', 'List of variants: position, change, genotype, quality'],
    ['Depth (×)', 'How many reads cover a base; exomes aim for ≥ 100× mean, ≥ 20× almost everywhere'],
    ['VAF', 'Variant allele fraction: share of reads with the change (germline ≈ 50% or 100%; tumours lower)'],
    ['gnomAD AF', 'How common the variant is in the population (>1% is too common for most rare diseases)'],
    ['HGVS', 'Standard variant names: c. (cDNA) and p. (protein), e.g. c.1799T>A p.Val600Glu'],
  ], 0.5, 1.8, 12.3, [2.3, 10.0], 16, 0.6);
  d.footer(s);

  await d.closing('Good practice from day one', [
    'Education and research only: never report results for patient care.',
    'Use pseudonymous sample names (no names, no hospital numbers).',
    'Respect licences: REVEL, AlphaMissense, SpliceAI, COSMIC, OncoKB are non-commercial.',
    'Record versions: the report lists every tool and database used.',
    'Next: deck 2 (germline analysis) and deck 3 (somatic analysis).',
  ], 'FaShieldAlt');
  await d.save();
}

// =====================================================================================================================
async function deck2() {
  const d = new Deck('AFLA_2_Germline_Analysis.pptx', 'AFLA 2: Germline analysis');
  let s = await d.cover('AFLA BEGINNER GUIDE 2 OF 3', 'Germline analysis', 'From reads to a classified variant: QC, filtering, inheritance, ACMG/AMP evidence and the case report', 'FaDna');

  s = d.content(); d.title(s, 'What happens when you click Run', 'Every box can be switched on or off in the form');
  d.steps(s, [
    ['Clean reads', 'fastp removes adapters and poor-quality ends; writes a QC report.'],
    ['Align', 'bwa places reads on GRCh38; duplicates marked (capture) or primers clipped (amplicon).'],
    ['Call variants', 'GATK or DeepVariant (GPU). Families are genotyped together.'],
    ['Extra layers', 'CNV (CNVkit), runs of homozygosity, structural variants (Manta).'],
    ['Annotate', 'VEP adds genes, HGVS, gnomAD, ClinVar, REVEL, AlphaMissense; AFLA adds ACMG evidence and HPO ranking.'],
  ], 0.5, 1.9, 12.3);
  d.footer(s);

  s = d.content(); d.title(s, 'Setting up a case', 'Optional fields that make the report much smarter');
  await d.cards(s, [
    ['FaUsers', 'Sample sheet (families)', 'CSV with sample, role, sex, family, hpo. Family members are called together, so de novo and compound heterozygous variants can be recognised.'],
    ['FaUserMd', 'HPO terms', 'The patient\'s features as HPO codes, e.g. HP:0001250 (seizure). Genes are ranked by how well their known phenotypes match.', C.mint],
    ['FaListOl', 'Gene list / panel', 'Genes to focus on, or a PanelApp panel chosen inside the report: a "virtual panel" that avoids incidental findings.', C.coral],
    ['FaIdBadge', 'Case ID', 'A pseudonym printed on the report. Never use a patient\'s name.'],
  ], 0.5, 1.75, 12.3, 4.9, 2);
  d.footer(s);

  s = d.content(); d.title(s, 'Tab 1: Quality', 'Is the sequencing good enough to trust a negative result?');
  d.shot(s, 'g_quality.png', 0.5, 1.6, 7.6, 'Real report: GIAB trio, chromosome 20 exome');
  d.bullets(s, [['Mapped reads', '≥ 98% for human DNA.'], ['Duplicates', 'exomes often 5-20%.'],
    ['Mean depth', 'exome ≥ 100×.'], ['≥ 20×', 'aim for ≥ 95% of targets.'], ['Ti/Tv, het/hom', 'sanity checks of the calls.'],
    ['Low-coverage list', 'regions where a variant could be missed.']], {x: 8.5, y: 1.7, w: 4.3, h: 4.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'Tab 2: Variants', 'Presets do the first filtering for you');
  d.shot(s, 'g_variants.png', 0.5, 1.6, 7.6, 'Presets, filters and the variant table');
  d.bullets(s, [['Prioritised', 'ACMG points + phenotype match + your gene list.'], ['Rare, protein-affecting', 'gnomAD ≤ 1%, HIGH/MODERATE impact.'],
    ['ClinVar P/LP', 'already reported as disease-causing.'], ['De novo / Recessive', 'for trios.'],
    ['Click a column', 'to sort; a row to open details.']], {x: 8.5, y: 1.7, w: 4.3, h: 4.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'Filtering is a funnel', 'Real numbers from one exome slice (HG002, chromosome 20)');
  s.addChart(d.pres.charts.BAR, [{name: 'Variants', labels: ['All calls', 'PASS', 'Protein-affecting, rare (≤1%)', 'VUS or worse (suggested)'], values: [2104, 2037, 22, 22]}], {
    x: 0.5, y: 1.7, w: 7.8, h: 4.9, barDir: 'bar', chartColors: [C.teal], showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: C.ink,
    catAxisLabelColor: C.ink, valAxisLabelColor: C.muted, valGridLine: {color: 'E6ECEF', size: 0.5}, catGridLine: {style: 'none'},
    showLegend: false, showTitle: true, title: 'Variants left after each filter', titleColor: C.ink, titleFontSize: 14, catAxisOrientation: 'maxMin'});
  d.bullets(s, ['A whole exome has 20,000-50,000 variants; most are common and harmless.', 'Filters remove what cannot explain a rare disease.',
    'What remains is reviewed one by one: that is interpretation.', 'Too strict a filter can hide the answer: always know what you removed.'],
    {x: 8.7, y: 1.9, w: 4.1, h: 4.6, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'The variant card', 'Everything about one variant, plus the family');
  d.shot(s, 'g_detail.png', 0.5, 1.6, 7.6, 'Detail card with family genotypes and links');
  d.bullets(s, [['Gene, transcript', 'MANE Select transcript, exon, HGVS names.'], ['Frequency', 'gnomAD exomes/genomes, max population.'],
    ['Predictions', 'REVEL, AlphaMissense, SpliceAI.'], ['Family', 'genotype, depth and VAF of each member.'],
    ['Links', 'gnomAD, ClinVar, UCSC, ClinGen, OMIM, PubMed, PanelApp.'], ['Online check', 'current gnomAD/ClinVar with one click.']],
    {x: 8.5, y: 1.7, w: 4.3, h: 4.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'Reading a trio', 'Inheritance labels AFLA adds automatically');
  d.table(s, [['Label', 'Child', 'Mother', 'Father', 'Think of'],
    ['de novo', 'het (≈50%)', 'ref', 'ref', 'dominant disorders, new mutations'],
    ['possible de novo (low VAF)', 'het < 25%', 'ref', 'ref', 'usually artefact; sometimes mosaic'],
    ['homozygous', 'hom', 'het', 'het', 'recessive disorders (consanguinity)'],
    ['compound heterozygous', 'het + het', 'one', 'the other', 'recessive, two different variants'],
    ['hemizygous (X-linked)', 'hom (male)', 'het', 'ref', 'X-linked recessive in boys'],
    ['inherited from ...', 'het', 'het', 'ref', 'dominant if that parent is affected'],
  ], 0.5, 1.7, 12.3, [3.2, 1.8, 1.4, 1.4, 4.5], 16, 0.55);
  s.addText('In our GIAB test, all 5 "de novo-looking" calls had 8-17% of reads: artefacts. True constitutional de novo variants sit near 50%.',
    {x: 0.5, y: 5.75, w: 12.3, h: 0.7, fontFace: BODY, fontSize: 15, color: C.coral, bold: true, margin: 0, isTextBox: true});
  d.footer(s);

  s = d.content(); d.title(s, 'ACMG/AMP evidence panel', 'Tick the evidence; the class updates live');
  d.shot(s, 'g_acmg.png', 0.5, 1.6, 7.6, 'All 26 criteria; suggested ones pre-ticked with the reason');
  d.bullets(s, [['Suggested', 'from data: PVS1, PS1, PM2, PM4, PM5, PP3/BP4, BA1, BS1, BP7, PM6, PM3.'],
    ['Never automatic', 'PS3, PS4, PP1, PP4, BS3, BS4, BP5: need literature, segregation or phenotype.'],
    ['Strength', 'change it with the drop-down (e.g. PP3 strong for REVEL ≥ 0.932).'],
    ['Note', 'write your reasoning; star ☆ to report.']], {x: 8.5, y: 1.7, w: 4.3, h: 4.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'From evidence to a class', 'Bayesian points (Tavtigian et al. 2020)');
  d.stat(s, '8', 'Very strong (e.g. PVS1)', 0.5, 1.8, 2.8);
  d.stat(s, '4', 'Strong (e.g. PS1, PP3 strong)', 3.6, 1.8, 2.8);
  d.stat(s, '2', 'Moderate (e.g. PM4, PM5)', 6.7, 1.8, 2.8);
  d.stat(s, '1', 'Supporting (e.g. PM2, PP3). Benign criteria count negative', 9.8, 1.8, 2.8, C.mint);
  d.table(s, [['Total points', '≥ 10', '6 to 9', '0 to 5', '-1 to -6', '≤ -7 (or BA1)'],
    ['Class', 'Pathogenic', 'Likely pathogenic', 'Uncertain significance', 'Likely benign', 'Benign']],
    0.5, 4.2, 12.3, [2.3, 2.0, 2.0, 2.0, 2.0, 2.0], 15);
  s.addText('Example: stop-gain in a loss-of-function intolerant gene (PVS1 = 8) absent from gnomAD (PM2 = 1) and de novo (PM6 = 2) → 11 points → Pathogenic.',
    {x: 0.5, y: 5.6, w: 12.3, h: 0.8, fontFace: BODY, fontSize: 15, color: C.ink, italic: true, margin: 0, isTextBox: true});
  d.footer(s);

  s = d.content(); d.title(s, 'Phenotype matching (HPO)', 'Which genes fit the patient?');
  await d.cards(s, [
    ['FaSearch', 'You enter features', 'e.g. seizure (HP:0001250) + global developmental delay (HP:0001263).'],
    ['FaProjectDiagram', 'AFLA compares', 'with each gene\'s known features in the Human Phenotype Ontology (semantic similarity, 0-1).', C.mint],
    ['FaSortAmountDown', 'Genes rise', 'In our test, epilepsy genes (SLC12A5, KCNB1, KCNQ2, EEF1A2) ranked top on chromosome 20.', C.coral],
  ], 0.5, 1.8, 12.3, 2.9, 3);
  d.bullets(s, ['A high HPO score is support, not proof: the healthy GIAB sample has none of these diseases.',
    'Precise, specific terms help more than general ones ("infantile spasms" beats "seizure").'], {x: 0.5, y: 5.0, w: 12.3, h: 1.5});
  d.footer(s);

  s = d.content(); d.title(s, 'Copy number and homozygosity', 'Beyond single-letter changes');
  d.shot(s, 'g_cnv.png', 0.5, 1.6, 7.6, 'CNVkit plot and segments (reference: other samples of the run)');
  d.bullets(s, [['log2 ≈ -1', 'one copy lost; ≈ +0.58 one copy gained.'], ['Reference matters', '"pooled" (3+ samples, same kit) or your own; "flat" is weak.'],
    ['Confirm', 'CNVs by MLPA, array or qPCR.'], ['ROH', 'long homozygous stretches: consanguinity, and where recessive genes hide.']],
    {x: 8.5, y: 1.7, w: 4.3, h: 4.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'Exercise mode and the case report', 'Learn by doing, then compare');
  d.shot(s, 'g_exercise.png', 0.5, 1.65, 5.95, 'Exercise mode hides ClinVar and suggestions');
  d.shot(s, 'g_report.png', 6.85, 1.65, 5.95, 'Printable case report built from your ☆ choices');
  d.bullets(s, ['Students classify blind, then untick exercise mode to compare.', '"Save my work" keeps stars, criteria and notes in a small file for marking.'],
    {x: 0.5, y: 6.0, w: 12.3, h: 0.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'How accurate is it?', 'Scored against Genome in a Bottle truth sets (chr20 exome targets, GATK)');
  s.addChart(d.pres.charts.BAR, [
    {name: 'SNV F1', labels: ['HG002', 'HG003', 'HG004'], values: [0.9985, 0.9985, 0.9971]},
    {name: 'Indel F1', labels: ['HG002', 'HG003', 'HG004'], values: [0.9014, 0.9492, 0.8696]}], {
    x: 0.5, y: 1.7, w: 7.8, h: 4.8, barDir: 'col', barGrouping: 'clustered', chartColors: [C.teal, C.coral], showValue: true,
    dataLabelPosition: 'outEnd', dataLabelFormatCode: '0.00', valAxisMinVal: 0.8, valAxisMaxVal: 1.0, valAxisLabelFormatCode: '0.00',
    valGridLine: {color: 'E6ECEF', size: 0.5}, catGridLine: {style: 'none'}, catAxisLabelColor: C.ink, valAxisLabelColor: C.muted,
    showLegend: true, legendPos: 'b', showTitle: true, title: 'F1 score (1.00 = perfect)', titleColor: C.ink, titleFontSize: 14});
  d.bullets(s, ['SNVs: > 99.7% found, almost no false calls.', 'Indels are harder (small numbers here: ~30 per sample).',
    'Main false calls: low-VAF indels in homopolymers; the LowVAF label removes most of them.', 'Repeat this benchmark yourself: scripts/afla-benchmark.sh (deck exercise 2).'],
    {x: 8.7, y: 1.9, w: 4.1, h: 4.6, fontSize: 15});
  d.footer(s);

  await d.closing('Germline pitfalls to remember', [
    'No coverage, no conclusion: check low-coverage regions before calling a result negative.',
    'Low VAF "heterozygous" calls are usually artefacts; confirm anything important by Sanger.',
    'Pseudogenes and repeats (PMS2, SMN1, CYP2D6, repeat expansions) are not reliable with short reads.',
    'ClinVar changes: re-check with the live button; frequencies matter as much as predictions.',
    'Suggestions are a start: the classification is yours, with literature and family data.',
  ], 'FaExclamationTriangle');
  await d.save();
}

// =====================================================================================================================
async function deck3() {
  const d = new Deck('AFLA_3_Somatic_Analysis.pptx', 'AFLA 3: Somatic analysis');
  let s = await d.cover('AFLA BEGINNER GUIDE 3 OF 3', 'Somatic (tumour) analysis', 'Low-frequency variants, UMIs and amplicons, tumour-only vs paired, TMB, MSI, evidence and tiers', 'FaMicroscope');

  s = d.content(); d.title(s, 'Germline vs somatic', 'Same reads, different questions');
  d.table(s, [['', 'Germline', 'Somatic'],
    ['Where the variant is', 'every cell, from conception', 'only in tumour cells'],
    ['Expected VAF', '≈ 50% (het) or 100% (hom)', 'anything: 1-60%, depends on purity and clonality'],
    ['Caller', 'GATK HaplotypeCaller / DeepVariant', 'GATK Mutect2'],
    ['Depth needed', '≥ 20× per base', 'often ≥ 200-500× for panels'],
    ['Main risk', 'missing a variant in low coverage', 'calling artefacts or germline variants as somatic'],
    ['Interpretation', 'ACMG/AMP pathogenicity', 'AMP/ASCO/CAP tiers (clinical actionability)'],
  ], 0.5, 1.8, 12.3, [2.8, 4.5, 5.0], 16, 0.62);
  d.footer(s);

  s = d.content(); d.title(s, 'Running a tumour', 'EPI2ME → AFLA somatic');
  d.steps(s, [
    ['Input', 'Tumour FASTQ/BAM; add the normal (blood) sample if you have it.'],
    ['Pairing', 'Sample sheet: roles tumour/normal with the same family (patient) ID, or type the normal\'s name.'],
    ['Library', 'Amplicon? tick it + primer BED. UMIs? inline or read_name.'],
    ['Tumour type', 'Free text, e.g. "colorectal cancer": evidence in the same tumour type → tier I.'],
    ['Run', 'Mutect2, CNV, MSI, TMB, evidence, tiers, report.'],
  ], 0.5, 1.9, 12.3);
  d.footer(s);

  s = d.content(); d.title(s, 'Amplicons and UMIs, simply', 'Two chemistries that change the analysis');
  await d.cards(s, [
    ['FaCut', 'Primer clipping', 'Primer bases copy the oligo, not the patient. AFLA soft-clips them using the primer BED, so they cannot hide or fake variants at amplicon ends. In a test, 335,038 reads were clipped with 98% amplicon uniformity.'],
    ['FaTags', 'UMI consensus', 'Each original DNA molecule carries a barcode (UMI). Reads with the same UMI are merged: random PCR and sequencing errors disappear. In a simulation, AFLA recovered the planted families of 1-4 reads exactly.', C.coral],
  ], 0.5, 1.8, 12.3, 3.5, 2);
  d.bullets(s, ['Read structures: "8M+T 8M+T" = 8-base UMI on both reads; "+T 12M11S+T" = QIAseq (UMI + spacer on read 2).',
    'Illumina manifest → primer BED: python3 scripts/manifest_to_primers.py manifest.txt mypanel'], {x: 0.5, y: 5.6, w: 12.3, h: 1.1, fontSize: 14});
  d.footer(s);

  s = d.content(); d.title(s, 'Tumour-only or tumour + normal?', 'The normal sample is the best germline filter');
  await d.cards(s, [
    ['FaVial', 'Tumour + matched normal', 'Variants also in the normal are inherited, not tumour. Most reliable; needed for accurate TMB.', C.mint],
    ['FaVials', 'Tumour-only', 'Germline variants must be guessed from gnomAD, the panel of normals and VAF. AFLA shows an "origin hint": somatic candidate / possible germline (VAF) / likely germline (population).', C.coral],
  ], 0.5, 1.8, 12.3, 3.0, 2);
  s.addText('Practice data: an in-silico "tumour" made by mixing 20% of one person\'s reads into another\'s. Their private variants appear at ≈10-15% VAF, and common polymorphisms are correctly rejected as germline.',
    {x: 0.5, y: 5.2, w: 12.3, h: 1.1, fontFace: BODY, fontSize: 15, italic: true, color: C.ink, margin: 0, isTextBox: true});
  d.footer(s);

  s = d.content(); d.title(s, 'Tumour-level biomarkers', 'TMB and MSI in the Quality tab');
  d.shot(s, 's_quality.png', 0.5, 1.6, 7.6, 'Somatic report: QC tiles, base-change spectrum, TMB, MSI, tiers');
  d.bullets(s, [['TMB', 'coding mutations per Mb. Panels < 1 Mb are imprecise; tumour-only inflates it.'],
    ['MSI', '% unstable microsatellites (msisensor-pro). Cut-offs must be calibrated per assay.'],
    ['Base-change spectrum', 'one dominant unusual change (e.g. T>C) points to artefacts.']], {x: 8.5, y: 1.7, w: 4.3, h: 4.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'Tiers: how actionable is a variant?', 'AMP/ASCO/CAP 2017, suggested by AFLA, decided by you');
  const tiers = [['I', 'Strong clinical significance', 'Level A/B evidence (CIViC) or OncoKB level 1/2 in THIS tumour type', C.red],
    ['II', 'Potential clinical significance', 'A/B in another tumour type, level C/D, OncoKB 3/4, recurrent COSMIC hotspot', C.coral],
    ['III', 'Unknown significance', 'No evidence found, rare in the population', C.gold],
    ['IV', 'Benign or likely benign', 'Common in the population (≥ 1%) or ClinVar benign', C.green]];
  tiers.forEach(([t, h, b, col], i) => {
    const y = 1.8 + i * 1.2;
    s.addShape(d.pres.shapes.ROUNDED_RECTANGLE, {x: 0.5, y, w: 12.3, h: 1.0, fill: {color: C.light}, line: {color: C.light}, rectRadius: 0.1});
    s.addShape(d.pres.shapes.OVAL, {x: 0.7, y: y + 0.12, w: 0.76, h: 0.76, fill: {color: col}, line: {color: col}});
    s.addText(t, {x: 0.7, y: y + 0.12, w: 0.76, h: 0.76, fontFace: HEAD, fontSize: 20, bold: true, color: C.white, align: 'center', valign: 'middle', margin: 0, isTextBox: true});
    s.addText(h, {x: 1.7, y: y + 0.1, w: 3.8, h: 0.8, fontFace: HEAD, fontSize: 17, bold: true, color: C.ink, valign: 'middle', margin: 0, isTextBox: true});
    s.addText(b, {x: 5.6, y: y + 0.1, w: 7.0, h: 0.8, fontFace: BODY, fontSize: 15, color: C.ink, valign: 'middle', margin: 0, isTextBox: true});
  });
  d.footer(s);

  s = d.content(); d.title(s, 'Variants tab (somatic)', 'Tier, origin hint and evidence in one view');
  d.shot(s, 's_variants.png', 0.5, 1.6, 7.6, 'Presets: Tier I-II, Somatic candidates, All');
  d.bullets(s, [['Origin hint', 'somatic candidate vs likely germline.'], ['Tier', 'hover to see why.'],
    ['Evidence', 'CIViC items, OncoKB level, COSMIC count.'], ['Details', 'click a row: evidence table with therapies and links.']],
    {x: 8.5, y: 1.7, w: 4.3, h: 4.9, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'Evidence sources', 'All free for education; some need registration');
  await d.cards(s, [
    ['FaBookMedical', 'CIViC', 'Open (CC0) expert-curated cancer evidence: therapies, diagnosis, prognosis. Downloaded by afla-setup.sh.'],
    ['FaKey', 'OncoKB', 'Precision oncology knowledge base. Free academic token; queried online during the run.', C.coral],
    ['FaDatabase', 'COSMIC', 'How often a mutation is seen in cancers. Free for academic use after registration; you download it.', C.mint],
    ['FaClipboardCheck', 'ClinVar somatic', 'Oncogenicity and clinical-impact classifications (ONC/SCI fields) in the same ClinVar file.'],
  ], 0.5, 1.75, 12.3, 4.9, 2);
  d.footer(s);

  s = d.content(); d.title(s, 'Copy number and fusions in tumours', 'Amplifications, deletions, rearrangements');
  await d.cards(s, [
    ['FaChartLine', 'CNV (CNVkit)', 'Gains/losses vs the normal (or other normals). Strong amplifications/deletions are matched to CIViC (e.g. ERBB2 amplification). Purity dilutes log2 ratios.'],
    ['FaRandom', 'Fusions (Manta)', 'Translocations between two genes appear as fusion candidates, only if the breakpoint lies near baited regions. Confirm by RNA or FISH.', C.coral],
  ], 0.5, 1.8, 12.3, 3.2, 2);
  d.bullets(s, ['Exome/panel CNV is screening-level: confirm clinically relevant changes by another method.',
    'RNA fusion panels (e.g. anchored multiplex PCR) are not supported yet.'], {x: 0.5, y: 5.3, w: 12.3, h: 1.3, fontSize: 15});
  d.footer(s);

  s = d.content(); d.title(s, 'Practice exercise', 'Work it through, then discuss');
  d.steps(s, [
    ['Run', 'AFLA somatic on the practice tumour + normal (samples.csv).'],
    ['Predict', 'Before looking: what VAF do you expect for a 20% contamination?'],
    ['Check', 'VAF column, origin hints, TMB and MSI.'],
    ['Tier', 'Explain one tier I-IV each; remove the tumour type and compare.'],
    ['Report', 'Star findings, write interpretation, print the somatic case report.'],
  ], 0.5, 1.9, 12.3);
  d.footer(s);

  await d.closing('Somatic pitfalls to remember', [
    'Tumour-only cannot prove a variant is somatic: consider a germline test for hereditary cancer genes.',
    'Low VAF + one dominant base change or strand-bias = suspect artefact (FFPE, PCR).',
    'Purity matters: a 30% tumour gives ≈15% VAF for heterozygous clonal variants.',
    'TMB and MSI thresholds are assay-specific; panels under 1 Mb are imprecise.',
    'Tiers are suggestions from databases; actionability needs a tumour board.',
  ], 'FaExclamationTriangle');
  await d.save();
}

(async () => { await deck1(); await deck2(); await deck3(); })().catch(e => { console.error(e); process.exit(1); });
