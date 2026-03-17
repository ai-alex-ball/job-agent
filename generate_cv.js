/**
 * generate_cv.js — Styled CV renderer
 *
 * Reads a JSON payload from stdin:
 *   { content: <CVContent>, accent: <hex string>, output: <file path> }
 *
 * Writes a formatted .docx to the given output path.
 *
 * Run:  echo '<json>' | node generate_cv.js
 */
import { writeFileSync } from 'fs';
import {
  Packer, Document, Paragraph, TextRun,
  Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, ShadingType,
  convertInchesToTwip,
} from 'docx';

// ── Read stdin ────────────────────────────────────────────────────────────────
const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const { content, accent: accentRaw, output } = JSON.parse(Buffer.concat(chunks).toString());

const ACCENT  = accentRaw.replace(/^#/, '');
const NAVY    = '1A1A2E';
const MIDGREY = '777777';
const ALTROW  = 'F5F5F5';

// A4 page, 0.62" margins → content width in twips
const MARGIN   = convertInchesToTwip(0.62);
const PAGE_W   = Math.round((8.27 - 2 * 0.62) * 1440);  // 10123 twips
const in2t     = n => Math.round(n * 1440);              // inches → twips
const pt2t     = n => n * 20;                            // pt → twips (spacing)
const hpt      = n => n * 2;                             // pt → half-pts (font size)

// ── Border constants ──────────────────────────────────────────────────────────
const noBorder  = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideH: noBorder, insideV: noBorder };

// ── Shading helpers ───────────────────────────────────────────────────────────
function altShade(i) { return { fill: i % 2 === 0 ? ALTROW : 'FFFFFF', type: ShadingType.CLEAR, color: 'auto' }; }
function lgShade()   { return { fill: ALTROW, type: ShadingType.CLEAR, color: 'auto' }; }

// ── Name + contact paragraphs ─────────────────────────────────────────────────
function makeNameContact() {
  return [
    new Paragraph({
      spacing: { before: 0, after: pt2t(2) },
      children: [new TextRun({ text: content.name.toUpperCase(), bold: true, size: hpt(28), color: NAVY, font: 'Arial' })],
    }),
    new Paragraph({
      spacing: { before: 0, after: pt2t(8) },
      children: [new TextRun({ text: content.contact.join('  |  '), size: hpt(9), color: MIDGREY, font: 'Arial' })],
    }),
  ];
}

// ── Career at a Glance: 2-row × 5-col light-grey table ───────────────────────
function makeStats() {
  const colW  = Math.floor(PAGE_W / content.stats.length);
  const shade = lgShade();

  return new Table({
    width:   { size: PAGE_W, type: WidthType.DXA },
    borders: noBorders,
    rows: [
      new TableRow({ children: content.stats.map(s => new TableCell({
        width:   { size: colW, type: WidthType.DXA },
        shading: shade,
        borders: { bottom: noBorder },
        margins: { top: pt2t(6), bottom: pt2t(1), left: pt2t(4), right: pt2t(4) },
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing:   { before: 0, after: 0 },
          children:  [new TextRun({ text: s.value, bold: true, size: hpt(16), color: NAVY, font: 'Arial' })],
        })],
      }))}),
      new TableRow({ children: content.stats.map(s => new TableCell({
        width:   { size: colW, type: WidthType.DXA },
        shading: shade,
        borders: { top: noBorder },
        margins: { top: pt2t(1), bottom: pt2t(6), left: pt2t(4), right: pt2t(4) },
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing:   { before: 0, after: 0 },
          children:  [new TextRun({ text: s.label, size: hpt(8), color: MIDGREY, font: 'Arial' })],
        })],
      }))}),
    ],
  });
}

// ── Section heading (ALL CAPS bold + accent underline) ────────────────────────
function sectionHeading(text) {
  return new Paragraph({
    spacing: { before: pt2t(11), after: pt2t(3) },
    border:  { bottom: { color: ACCENT, space: 1, style: BorderStyle.SINGLE, size: 6 } },
    children: [new TextRun({ text: text.toUpperCase(), bold: true, size: hpt(11), font: 'Arial' })],
  });
}

// ── Bullet paragraph (▸ in accent; split at ' --- ' for bold/normal) ──────────
function bulletPara(text, sizePt = 10) {
  const parts = text.split(' --- ');
  const sz = hpt(sizePt);

  const children = [
    new TextRun({ text: '▸  ', color: ACCENT, size: sz, font: 'Arial', bold: false }),
  ];

  if (parts.length > 1) {
    children.push(new TextRun({
      text: parts[0],
      bold: true,
      size: sz,
      font: 'Arial',
      color: '1A1A1A'
    }));
    children.push(new TextRun({
      text: ' — ' + parts.slice(1).join(' — '),
      bold: false,
      size: sz,
      font: 'Arial',
      color: '1A1A1A'
    }));
  } else {
    children.push(new TextRun({
      text: parts[0],
      bold: false,
      size: sz,
      font: 'Arial',
      color: '1A1A1A'
    }));
  }

  return new Paragraph({
    spacing: { before: pt2t(2), after: pt2t(2) },
    indent: { left: in2t(0.25), hanging: in2t(0.15) },
    children,
    run: { bold: false }
  });
}

// ── Job title row (two-column table) ─────────────────────────────────────────
function jobTitleTable(title, company, dates, location) {
  const leftW  = Math.round(PAGE_W * 0.65);
  const rightW = PAGE_W - leftW;
  const meta   = [location, dates].filter(Boolean).join('  |  ');

  return new Table({
    width:   { size: PAGE_W, type: WidthType.DXA },
    borders: noBorders,
    rows: [new TableRow({ children: [
      new TableCell({
        width:   { size: leftW, type: WidthType.DXA },
        borders: noBorders,
        margins: { top: 0, bottom: 0, left: 0, right: 0 },
        children: [new Paragraph({
          spacing: { before: pt2t(8), after: pt2t(2) },
          children: [
            new TextRun({ text: title + '  ', bold: true, size: hpt(11), font: 'Arial' }),
            new TextRun({ text: company,       bold: true, size: hpt(11), color: ACCENT, font: 'Arial' }),
          ],
        })],
      }),
      new TableCell({
        width:   { size: rightW, type: WidthType.DXA },
        borders: noBorders,
        margins: { top: 0, bottom: 0, left: 0, right: 0 },
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          spacing:   { before: pt2t(8), after: pt2t(2) },
          children:  [new TextRun({ text: meta, size: hpt(9), color: MIDGREY, font: 'Arial' })],
        })],
      }),
    ]})]
  });
}

// ── Skills table (two-column, alternating row shading) ────────────────────────
function makeSkillsTable() {
  const labelW = Math.round(PAGE_W * 0.22);
  const valW   = PAGE_W - labelW;

  return new Table({
    width:   { size: PAGE_W, type: WidthType.DXA },
    borders: noBorders,
    rows: content.skills.map((s, i) => new TableRow({ children: [
      new TableCell({
        width:   { size: labelW, type: WidthType.DXA },
        shading: altShade(i),
        margins: { top: pt2t(3), bottom: pt2t(3), left: in2t(0.05), right: in2t(0.05) },
        children: [new Paragraph({
          children: [new TextRun({ text: s.label, bold: true, size: hpt(9.5), font: 'Arial' })],
        })],
      }),
      new TableCell({
        width:   { size: valW, type: WidthType.DXA },
        shading: altShade(i),
        margins: { top: pt2t(3), bottom: pt2t(3), left: in2t(0.05), right: in2t(0.05) },
        children: [new Paragraph({
          children: [new TextRun({ text: s.values, size: hpt(9.5), font: 'Arial' })],
        })],
      }),
    ]})),
  });
}

// ── Assemble document children ────────────────────────────────────────────────
const children = [];

children.push(...makeNameContact());

// Professional Summary
children.push(sectionHeading('Professional Summary'));
children.push(new Paragraph({
  spacing: { before: pt2t(3), after: pt2t(6) },
  children: [new TextRun({ text: content.summary, size: hpt(10), font: 'Arial' })],
}));

// Career at a Glance
children.push(sectionHeading('Career at a Glance'));
children.push(makeStats());

// Recent Projects (optional)
if (content.projects && content.projects.length > 0) {
  children.push(sectionHeading('Recent Projects'));
  for (const proj of content.projects) {
    const header = proj.date ? `${proj.name}  (${proj.date})` : proj.name;
    children.push(new Paragraph({
      spacing: { before: pt2t(5), after: pt2t(2) },
      children: [new TextRun({ text: header, bold: true, size: hpt(10), font: 'Arial' })],
    }));
    for (const b of proj.bullets) children.push(bulletPara(b));
  }
}

// Experience
children.push(sectionHeading('Experience'));
for (const role of content.experience) {
  children.push(jobTitleTable(role.title, role.company, role.dates, role.location));
  for (const b of role.bullets) children.push(bulletPara(b));
}

// Earlier Career
if (content.earlier_career && content.earlier_career.length > 0) {
  children.push(new Paragraph({
    spacing: { before: pt2t(10), after: pt2t(3) },
    children: [new TextRun({ text: 'Earlier Career', bold: true, size: hpt(10), font: 'Arial' })],
  }));
  for (const role of content.earlier_career) {
    children.push(new Paragraph({
      spacing: { before: 0, after: pt2t(2) },
      children: [
        new TextRun({ text: role.company + ' — ', bold: true, size: hpt(10), font: 'Arial' }),
        new TextRun({ text: role.title,                        size: hpt(10), font: 'Arial' }),
        new TextRun({ text: `  (${role.dates})`,               size: hpt(9),  color: MIDGREY, font: 'Arial' }),
      ],
    }));
  }
}

// Education & Qualifications
children.push(sectionHeading('Education & Qualifications'));
for (const item of content.education) {
  children.push(new Paragraph({
    spacing: { before: pt2t(2), after: pt2t(2) },
    indent:  { left: in2t(0.25), hanging: in2t(0.15) },
    children: [new TextRun({ text: '▸  ' + item, size: hpt(9.5), font: 'Arial' })],
  }));
}

// Key Skills
children.push(sectionHeading('Key Skills'));
children.push(makeSkillsTable());

// ── Build & write ─────────────────────────────────────────────────────────────
const doc = new Document({
  sections: [{
    properties: {
      page: {
        margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN },
        size:   { width: Math.round(8.27 * 1440), height: Math.round(11.69 * 1440) },
      },
    },
    children,
  }],
});

const buffer = await Packer.toBuffer(doc);
writeFileSync(output, buffer);
process.stdout.write(`[generate_cv.js] Written: ${output}\n`);
