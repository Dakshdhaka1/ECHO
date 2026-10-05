package com.echo.service;

import com.echo.dto.Dtos.ReportDto;
import com.echo.exception.ApiException;
import com.echo.model.Plan;
import java.awt.Color;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import com.lowagie.text.Document;
import com.lowagie.text.Element;
import com.lowagie.text.Font;
import com.lowagie.text.FontFactory;
import com.lowagie.text.PageSize;
import com.lowagie.text.Paragraph;
import com.lowagie.text.Phrase;
import com.lowagie.text.pdf.PdfPCell;
import com.lowagie.text.pdf.PdfPTable;
import com.lowagie.text.pdf.PdfWriter;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

/** Report exports: CSV factor table (all plans) and a PDF executive report (Pro and Enterprise). */
@Service
public class ExportService {

    private final PlanService plans;

    public ExportService(PlanService plans) {
        this.plans = plans;
    }

    public byte[] csv(ReportDto r, Long userId) {
        plans.recordExport(userId, r.company().id());
        StringBuilder sb = new StringBuilder("pillar,factor,kind,value,score,peer_percentile,impact_points,note\n");
        for (JsonNode p : r.payload().path("pillars")) {
            for (JsonNode f : p.path("factors")) {
                sb.append(csvCell(p.path("label").asString())).append(',')
                  .append(csvCell(f.path("label").asString())).append(',')
                  .append(f.path("kind").asString()).append(',')
                  .append(csvCell(f.path("display_value").asString(""))).append(',')
                  .append(num(f.path("score"))).append(',')
                  .append(num(f.path("peer_percentile"))).append(',')
                  .append(num(f.path("impact"))).append(',')
                  .append(csvCell(f.path("note").asString(""))).append('\n');
            }
        }
        sb.append("\nhealth_score,").append(r.healthScore() == null ? "" : r.healthScore())
          .append("\nband,").append(r.band())
          .append("\nconfidence,").append(r.confidence())
          .append("\nas_of,").append(r.asOf())
          .append("\ndisclaimer,").append(csvCell(r.payload().path("disclaimer").asString())).append('\n');
        return sb.toString().getBytes(StandardCharsets.UTF_8);
    }

    public byte[] pdf(ReportDto r, Long userId) {
        Plan plan = plans.planOf(userId);
        if (!plan.pdfExport()) {
            throw ApiException.planLimit("PDF reports are part of the Pro and Enterprise plans.");
        }
        plans.recordExport(userId, r.company().id());
        JsonNode t = r.payload();
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        Document doc = new Document(PageSize.A4, 40, 40, 40, 40);
        PdfWriter.getInstance(doc, out);
        doc.open();
        Font h1 = FontFactory.getFont(FontFactory.HELVETICA_BOLD, 18, new Color(17, 24, 39));
        Font h2 = FontFactory.getFont(FontFactory.HELVETICA_BOLD, 12, new Color(55, 65, 81));
        Font body = FontFactory.getFont(FontFactory.HELVETICA, 9, new Color(31, 41, 55));
        Font small = FontFactory.getFont(FontFactory.HELVETICA_OBLIQUE, 7.5f, new Color(107, 114, 128));

        doc.add(new Paragraph("ECHO Corporate Health Report", h1));
        doc.add(new Paragraph(r.company().name() + (r.company().ticker() == null ? "" : " (" + r.company().ticker() + ")")
                + "  |  as of " + r.asOf() + "  |  generated " + r.generatedAt().toLocalDate(), body));
        if (t.path("case_study").isObject()) {
            doc.add(new Paragraph(t.path("case_study").path("note").asString(), small));
        }
        doc.add(new Paragraph(" "));
        String score = r.healthScore() == null ? "n/a" : r.healthScore() + "/100";
        doc.add(new Paragraph("Health score: " + score + "   Band: " + r.band() + "   Confidence: "
                + Math.round(r.confidence().doubleValue() * 100) + "%", h2));
        JsonNode distress = t.path("distress");
        if (distress.path("available").asBoolean(false)) {
            doc.add(new Paragraph(String.format(Locale.ROOT, "12-month distress probability (ML): %.2f%% - %s band",
                    distress.path("probability_12m").asDouble() * 100, distress.path("risk_band").asString()), body));
        }
        doc.add(new Paragraph(" "));
        doc.add(new Paragraph("Executive summary (" + t.path("summary").path("generator").asString() + ")", h2));
        doc.add(new Paragraph(t.path("summary").path("text").asString(), body));
        doc.add(new Paragraph(" "));

        doc.add(new Paragraph("Pillars and factors", h2));
        PdfPTable table = new PdfPTable(new float[] {2.2f, 3.6f, 0.8f, 1.4f, 0.9f, 0.9f});
        table.setWidthPercentage(100);
        table.setSpacingBefore(4);
        for (String head : new String[] {"Pillar", "Factor", "Kind", "Value", "Score", "Impact"}) {
            PdfPCell cell = new PdfPCell(new Phrase(head, h2));
            cell.setBackgroundColor(new Color(243, 244, 246));
            table.addCell(cell);
        }
        for (JsonNode p : t.path("pillars")) {
            String pillar = p.path("label").asString() + (p.path("score").isNumber()
                    ? String.format(Locale.ROOT, " (%.0f)", p.path("score").asDouble()) : " (n/a)");
            if (p.path("factors").isEmpty()) {
                table.addCell(new Phrase(pillar, body));
                PdfPCell reason = new PdfPCell(new Phrase("Unavailable: " + p.path("unavailable_reason").asString(""), small));
                reason.setColspan(5);
                table.addCell(reason);
                continue;
            }
            for (JsonNode f : p.path("factors")) {
                table.addCell(new Phrase(pillar, body));
                table.addCell(new Phrase(f.path("label").asString(), body));
                table.addCell(new Phrase(f.path("kind").asString(), body));
                table.addCell(new Phrase(f.path("display_value").asString("-"), body));
                table.addCell(new Phrase(f.path("score").isNumber() ? String.format(Locale.ROOT, "%.0f", f.path("score").asDouble()) : "-", body));
                table.addCell(new Phrase(String.format(Locale.ROOT, "%+.1f", f.path("impact").asDouble()), body));
            }
        }
        doc.add(table);
        doc.add(new Paragraph(" "));
        doc.add(new Paragraph("Warning signals", h2));
        if (t.path("signals").isEmpty()) {
            doc.add(new Paragraph("None.", body));
        }
        for (JsonNode s : t.path("signals")) {
            doc.add(new Paragraph("[" + s.path("severity").asString() + ", " + s.path("kind").asString() + "] "
                    + s.path("message").asString(), body));
        }
        doc.add(new Paragraph(" "));
        Paragraph disclaimer = new Paragraph(t.path("disclaimer").asString(), small);
        disclaimer.setAlignment(Element.ALIGN_JUSTIFIED);
        doc.add(disclaimer);
        doc.close();
        return out.toByteArray();
    }

    private static String num(JsonNode n) {
        return n.isNumber() ? String.format(Locale.ROOT, "%.4f", n.asDouble()) : "";
    }

    private static String csvCell(String s) {
        if (s == null) return "";
        return s.contains(",") || s.contains("\"") || s.contains("\n") ? "\"" + s.replace("\"", "\"\"") + "\"" : s;
    }
}
