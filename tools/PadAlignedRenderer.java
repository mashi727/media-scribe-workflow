/**
 * PadAlignedRenderer - PAD renderer with depth-based column alignment
 *
 * This renderer ensures that boxes at the same depth level align vertically,
 * creating a proper columnar PAD layout.
 *
 * Usage: java -cp PadTools.jar:libs/* PadAlignedRenderer input.spd output.png [scale]
 */

import padtools.core.formats.spd.SPDParser;
import padtools.core.formats.spd.ParseErrorReceiver;
import padtools.core.formats.spd.ParseErrorException;
import padtools.core.models.*;

import java.awt.*;
import java.awt.image.BufferedImage;
import java.awt.geom.*;
import java.io.*;
import java.util.*;
import java.util.List;
import javax.imageio.ImageIO;

public class PadAlignedRenderer {

    // Layout constants
    private static final int MARGIN = 20;
    private static final int BOX_HEIGHT = 32;
    private static final int BOX_MIN_WIDTH = 100;
    private static final int BOX_MAX_WIDTH = 180;  // Maximum width before text wrapping
    private static final int COLUMN_GAP = 8;
    private static final int ROW_GAP = 4;
    private static final int BAR_WIDTH = 6;  // For call box double lines
    private static final int TERMINAL_RADIUS = 16;
    private static final int LINE_HEIGHT = 16;
    private static final int TEXT_PADDING = 8;

    // Fonts
    private static final Font MAIN_FONT = new Font("Hiragino Kaku Gothic ProN", Font.PLAIN, 12);
    private static final Font COMMENT_FONT = new Font("Hiragino Kaku Gothic ProN", Font.PLAIN, 10);

    // Colors - Original PADtools style (black & white)
    private static final Color STROKE_COLOR = Color.BLACK;
    private static final Color FILL_COLOR = Color.WHITE;
    private static final Color TEXT_COLOR = Color.BLACK;

    // Layout state
    private Map<Integer, Double> columnWidths = new HashMap<>();
    private Map<Integer, Double> columnX = new HashMap<>();
    private Graphics2D g2d;
    private FontMetrics fm;
    private FontMetrics fmComment;
    private double scale = 2.0;

    public static void main(String[] args) {
        if (args.length < 2) {
            System.err.println("Usage: java PadAlignedRenderer input.spd output.png [scale]");
            System.exit(1);
        }

        File fileIn = new File(args[0]);
        File fileOut = new File(args[1]);
        double scale = args.length > 2 ? Double.parseDouble(args[2]) : 2.0;

        try {
            new PadAlignedRenderer().render(fileIn, fileOut, scale);
            System.out.println("Generated: " + fileOut.getAbsolutePath());
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    public void render(File input, File output, double scale) throws Exception {
        this.scale = scale;

        // Parse SPD file
        String content = readFile(input);
        PADModel model = SPDParser.parse(content, new ParseErrorReceiver() {
            public boolean receiveParseError(String message, int line, ParseErrorException ex) {
                System.err.println("Parse error at line " + line + ": " + message);
                return false;
            }
        });

        if (model == null || model.getTopNode() == null) {
            throw new Exception("Failed to parse SPD file");
        }

        // Create temporary image for measurements
        BufferedImage tmpImg = new BufferedImage(1, 1, BufferedImage.TYPE_INT_RGB);
        g2d = tmpImg.createGraphics();
        g2d.setFont(MAIN_FONT);
        fm = g2d.getFontMetrics(MAIN_FONT);
        fmComment = g2d.getFontMetrics(COMMENT_FONT);

        // Pass 1: Calculate column widths
        calculateColumnWidths(model.getTopNode(), 0);

        // Calculate column X positions
        double x = MARGIN;
        int maxDepth = columnWidths.isEmpty() ? 0 : Collections.max(columnWidths.keySet());
        for (int depth = 0; depth <= maxDepth; depth++) {
            columnX.put(depth, x);
            x += columnWidths.getOrDefault(depth, (double)BOX_MIN_WIDTH) + COLUMN_GAP;
        }

        // Pass 2: Calculate total dimensions
        double totalWidth = x + MARGIN;
        double totalHeight = calculateHeight(model.getTopNode()) + MARGIN * 2;

        g2d.dispose();

        // Create final image
        int imgWidth = (int)(totalWidth * scale);
        int imgHeight = (int)(totalHeight * scale);
        BufferedImage img = new BufferedImage(imgWidth, imgHeight, BufferedImage.TYPE_INT_RGB);
        g2d = img.createGraphics();

        // Setup rendering
        g2d.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g2d.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        g2d.scale(scale, scale);

        // Fill background
        g2d.setColor(Color.WHITE);
        g2d.fillRect(0, 0, (int)totalWidth, (int)totalHeight);

        fm = g2d.getFontMetrics(MAIN_FONT);
        fmComment = g2d.getFontMetrics(COMMENT_FONT);

        // Draw PAD
        drawNode(model.getTopNode(), 0, MARGIN);

        g2d.dispose();

        // Write output
        ImageIO.write(img, "PNG", output);
    }

    private String readFile(File file) throws IOException {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line).append("\n");
            }
        }
        return sb.toString();
    }

    private void calculateColumnWidths(NodeBase node, int depth) {
        if (node == null) return;

        double width = getNodeWidth(node, depth);
        columnWidths.put(depth, Math.max(columnWidths.getOrDefault(depth, 0.0), width));

        // Process children
        if (node instanceof NodeListNode) {
            NodeListNode list = (NodeListNode) node;
            for (NodeBase child : list.getChildren()) {
                calculateColumnWidths(child, depth);
            }
        } else if (node instanceof IfNode) {
            IfNode ifNode = (IfNode) node;
            if (ifNode.getTrueNode() != null) {
                calculateColumnWidths(ifNode.getTrueNode(), depth + 1);
            }
            if (ifNode.getFalseNode() != null) {
                calculateColumnWidths(ifNode.getFalseNode(), depth + 1);
            }
        } else if (node instanceof SwitchNode) {
            SwitchNode sw = (SwitchNode) node;
            for (NodeBase caseChild : sw.getCases().values()) {
                calculateColumnWidths(caseChild, depth + 1);
            }
        } else if (node instanceof WithChildNode) {
            WithChildNode wc = (WithChildNode) node;
            if (wc.getChildNode() != null) {
                calculateColumnWidths(wc.getChildNode(), depth + 1);
            }
        }
    }

    private double getNodeWidth(NodeBase node, int depth) {
        String text = getNodeText(node);
        double textWidth = fm.stringWidth(text);
        double width;

        if (node instanceof CallNode) {
            width = Math.min(BOX_MAX_WIDTH, Math.max(BOX_MIN_WIDTH, textWidth + BAR_WIDTH * 4 + 16));
        } else if (node instanceof TerminalNode) {
            width = Math.min(BOX_MAX_WIDTH, Math.max(BOX_MIN_WIDTH, textWidth + TERMINAL_RADIUS * 2 + 8));
        } else if (node instanceof SwitchNode || node instanceof IfNode) {
            SwitchNode sw = node instanceof SwitchNode ? (SwitchNode) node : null;
            double maxCaseWidth = 0;
            if (sw != null) {
                for (String caseLabel : sw.getCases().keySet()) {
                    maxCaseWidth = Math.max(maxCaseWidth, fm.stringWidth(caseLabel));
                }
            }
            width = Math.min(BOX_MAX_WIDTH * 1.5, Math.max(BOX_MIN_WIDTH, textWidth + maxCaseWidth + 40));
        } else {
            width = Math.min(BOX_MAX_WIDTH, Math.max(BOX_MIN_WIDTH, textWidth + 16));
        }
        return width;
    }

    private String getNodeText(NodeBase node) {
        if (node instanceof ProcessNode) return ((ProcessNode) node).getText();
        if (node instanceof CallNode) return ((CallNode) node).getText();
        if (node instanceof TerminalNode) return ((TerminalNode) node).getText();
        if (node instanceof CommentNode) return ((CommentNode) node).getText();
        if (node instanceof LoopNode) return ((LoopNode) node).getText();
        if (node instanceof IfNode) return ((IfNode) node).getText();
        if (node instanceof SwitchNode) return ((SwitchNode) node).getText();
        return "";
    }

    // Wrap text to fit within maxWidth, breaking at logical points
    private List<String> wrapText(String text, double maxWidth, FontMetrics metrics) {
        List<String> lines = new ArrayList<>();
        if (text == null || text.isEmpty()) {
            lines.add("");
            return lines;
        }

        // If text fits in one line, return as is
        if (metrics.stringWidth(text) <= maxWidth) {
            lines.add(text);
            return lines;
        }

        // Try to break at logical points: →, 、, ・, spaces, or between characters
        StringBuilder currentLine = new StringBuilder();
        String[] segments = text.split("(?<=[→、・ ])|(?=[→、・ ])");

        for (String segment : segments) {
            String testLine = currentLine.toString() + segment;
            if (metrics.stringWidth(testLine) <= maxWidth) {
                currentLine.append(segment);
            } else {
                if (currentLine.length() > 0) {
                    lines.add(currentLine.toString().trim());
                    currentLine = new StringBuilder(segment);
                } else {
                    // Segment itself is too long, break by character
                    for (char c : segment.toCharArray()) {
                        testLine = currentLine.toString() + c;
                        if (metrics.stringWidth(testLine) <= maxWidth) {
                            currentLine.append(c);
                        } else {
                            if (currentLine.length() > 0) {
                                lines.add(currentLine.toString());
                            }
                            currentLine = new StringBuilder(String.valueOf(c));
                        }
                    }
                }
            }
        }

        if (currentLine.length() > 0) {
            lines.add(currentLine.toString().trim());
        }

        return lines.isEmpty() ? Arrays.asList("") : lines;
    }

    // Calculate box height based on text content
    private double getTextBoxHeight(String text, double maxWidth) {
        List<String> lines = wrapText(text, maxWidth - TEXT_PADDING * 2, fm);
        return Math.max(BOX_HEIGHT, lines.size() * LINE_HEIGHT + TEXT_PADDING * 2);
    }

    private double calculateHeight(NodeBase node) {
        if (node == null) return 0;

        if (node instanceof NodeListNode) {
            double height = 0;
            NodeListNode list = (NodeListNode) node;
            for (NodeBase child : list.getChildren()) {
                height += calculateHeight(child);
                height += ROW_GAP;
            }
            return height > 0 ? height - ROW_GAP : 0;
        } else if (node instanceof SwitchNode) {
            SwitchNode sw = (SwitchNode) node;
            double height = 0;
            for (Map.Entry<String, NodeBase> entry : sw.getCases().entrySet()) {
                String caseLabel = entry.getKey();
                NodeBase caseChild = entry.getValue();
                double caseBoxHeight = getTextBoxHeight(caseLabel, BOX_MAX_WIDTH);
                height += caseBoxHeight + ROW_GAP;
                height += calculateHeight(caseChild);
            }
            return height > 0 ? height - ROW_GAP : BOX_HEIGHT;
        } else if (node instanceof IfNode) {
            IfNode ifNode = (IfNode) node;
            double thenHeight = BOX_HEIGHT + ROW_GAP + calculateHeight(ifNode.getTrueNode());
            double elseHeight = ifNode.getFalseNode() != null ?
                BOX_HEIGHT + ROW_GAP + calculateHeight(ifNode.getFalseNode()) : 0;
            return thenHeight + elseHeight;
        } else if (node instanceof WithChildNode) {
            WithChildNode wc = (WithChildNode) node;
            String text = getNodeText(node);
            double boxHeight = getTextBoxHeight(text, BOX_MAX_WIDTH);
            double childHeight = calculateHeight(wc.getChildNode());
            return Math.max(boxHeight, childHeight);
        } else {
            String text = getNodeText(node);
            return getTextBoxHeight(text, BOX_MAX_WIDTH);
        }
    }

    private double drawNode(NodeBase node, int depth, double y) {
        if (node == null) return y;

        double x = columnX.getOrDefault(depth, (double)MARGIN);
        double width = columnWidths.getOrDefault(depth, (double)BOX_MIN_WIDTH);

        if (node instanceof NodeListNode) {
            NodeListNode list = (NodeListNode) node;
            for (NodeBase child : list.getChildren()) {
                y = drawNode(child, depth, y);
                y += ROW_GAP;
            }
            return y - ROW_GAP;
        } else if (node instanceof TerminalNode) {
            return drawTerminal((TerminalNode) node, x, y, width);
        } else if (node instanceof CommentNode) {
            return drawComment((CommentNode) node, x, y, width);
        } else if (node instanceof CallNode) {
            return drawCall((CallNode) node, depth, x, y, width);
        } else if (node instanceof ProcessNode) {
            return drawProcess((ProcessNode) node, depth, x, y, width);
        } else if (node instanceof SwitchNode) {
            return drawSwitch((SwitchNode) node, depth, x, y, width);
        } else if (node instanceof IfNode) {
            return drawIf((IfNode) node, depth, x, y, width);
        } else if (node instanceof LoopNode) {
            return drawLoop((LoopNode) node, depth, x, y, width);
        }

        return y + BOX_HEIGHT;
    }

    private double drawTerminal(TerminalNode node, double x, double y, double width) {
        String text = node.getText();
        double boxHeight = getTextBoxHeight(text, width);

        // Draw ellipse (original PADtools style)
        Ellipse2D ellipse = new Ellipse2D.Double(x, y, width, boxHeight);
        g2d.setColor(FILL_COLOR);
        g2d.fill(ellipse);
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.draw(ellipse);

        drawCenteredText(text, x, y, width, boxHeight, TEXT_COLOR, MAIN_FONT);
        return y + boxHeight;
    }

    private double drawComment(CommentNode node, double x, double y, double width) {
        String text = "(" + node.getText() + ")";  // Original PADtools style: parentheses
        double boxHeight = getTextBoxHeight(text, width);

        // No box, just text with parentheses (original PADtools style)
        drawCenteredText(text, x, y, width, boxHeight, TEXT_COLOR, MAIN_FONT);
        return y + boxHeight;
    }

    private double drawCall(CallNode node, int depth, double x, double y, double width) {
        String text = node.getText();
        double textBoxHeight = getTextBoxHeight(text, width - BAR_WIDTH * 2);
        double childHeight = calculateHeight(node.getChildNode());
        double boxHeight = Math.max(textBoxHeight, childHeight);

        // Draw call box with double vertical bars (original PADtools style)
        Rectangle2D rect = new Rectangle2D.Double(x, y, width, textBoxHeight);
        g2d.setColor(FILL_COLOR);
        g2d.fill(rect);
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.draw(rect);

        // Draw double vertical bars on left and right
        g2d.drawLine((int)(x + BAR_WIDTH), (int)y, (int)(x + BAR_WIDTH), (int)(y + textBoxHeight));
        g2d.drawLine((int)(x + width - BAR_WIDTH), (int)y,
                     (int)(x + width - BAR_WIDTH), (int)(y + textBoxHeight));

        drawCenteredText(text, x + BAR_WIDTH, y,
                        width - BAR_WIDTH * 2, textBoxHeight, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line connecting to children (on right side of box)
        if (node.getChildNode() != null && childHeight > 0) {
            double lineX = x + width;
            g2d.setColor(STROKE_COLOR);
            g2d.setStroke(new BasicStroke(1.5f));
            g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + boxHeight));

            drawNode(node.getChildNode(), depth + 1, y);
        }

        return y + boxHeight;
    }

    private double drawProcess(ProcessNode node, int depth, double x, double y, double width) {
        String text = node.getText();
        double textBoxHeight = getTextBoxHeight(text, width);
        double childHeight = calculateHeight(node.getChildNode());
        double boxHeight = Math.max(textBoxHeight, childHeight);

        // Draw process box (original PADtools style: simple rectangle)
        Rectangle2D rect = new Rectangle2D.Double(x, y, width, textBoxHeight);
        g2d.setColor(FILL_COLOR);
        g2d.fill(rect);
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.draw(rect);

        drawCenteredText(text, x, y, width, textBoxHeight, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line connecting to children (on right side of box)
        if (node.getChildNode() != null && childHeight > 0) {
            double lineX = x + width;
            g2d.setColor(STROKE_COLOR);
            g2d.setStroke(new BasicStroke(1.5f));
            g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + boxHeight));

            drawNode(node.getChildNode(), depth + 1, y);
        }

        return y + boxHeight;
    }

    private double drawSwitch(SwitchNode node, int depth, double x, double y, double width) {
        LinkedHashMap<String, NodeBase> cases = node.getCases();

        double conditionWidth = width * 0.35;
        double arrowWidth = 20;  // Width for arrow part
        double pennantX = x + conditionWidth;  // Pennant area starts after condition text
        double arrowX = pennantX + conditionWidth - arrowWidth;  // Arrow starts here

        // Calculate total height with wrapped text (no gaps between cases)
        double totalHeight = 0;
        for (Map.Entry<String, NodeBase> entry : cases.entrySet()) {
            String caseLabel = entry.getKey();
            NodeBase caseChild = entry.getValue();
            double caseBoxHeight = getTextBoxHeight(caseLabel, arrowX - pennantX);
            double childHeight = calculateHeight(caseChild);
            totalHeight += Math.max(caseBoxHeight, childHeight);
        }

        // Draw condition text on far left (original PADtools style)
        drawCenteredText(node.getText(), x, y, conditionWidth, totalHeight, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line at pennant left edge (connects all arrows)
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.drawLine((int)pennantX, (int)y, (int)pennantX, (int)(y + totalHeight));

        // Draw top border line
        g2d.drawLine((int)pennantX, (int)y, (int)arrowX, (int)y);

        // Draw cases (no horizontal separator lines between cases)
        double caseY = y;

        for (Map.Entry<String, NodeBase> entry : cases.entrySet()) {
            String caseLabel = entry.getKey();
            NodeBase caseChild = entry.getValue();
            double caseBoxHeight = getTextBoxHeight(caseLabel, arrowX - pennantX);
            double childHeight = calculateHeight(caseChild);
            double rowHeight = Math.max(caseBoxHeight, childHeight);

            // Draw arrow shape (chevron pointing right) - original PADtools style
            g2d.setColor(STROKE_COLOR);
            g2d.setStroke(new BasicStroke(1.5f));
            double arrowMidY = caseY + rowHeight / 2;
            // Top diagonal of arrow
            g2d.draw(new Line2D.Double(arrowX, caseY, arrowX + arrowWidth, arrowMidY));
            // Bottom diagonal of arrow
            g2d.draw(new Line2D.Double(arrowX + arrowWidth, arrowMidY, arrowX, caseY + rowHeight));

            // Draw case label as plain text (no box) - original PADtools style
            drawCenteredText(caseLabel, pennantX, caseY, arrowX - pennantX, rowHeight, TEXT_COLOR, MAIN_FONT);

            // Draw vertical line connecting to children (at arrow tip)
            if (caseChild != null && childHeight > 0) {
                double lineX = arrowX + arrowWidth;
                g2d.drawLine((int)lineX, (int)caseY, (int)lineX, (int)(caseY + rowHeight));
                drawNode(caseChild, depth + 1, caseY);
            }

            caseY += rowHeight;
        }

        // Draw bottom border line
        g2d.drawLine((int)pennantX, (int)(y + totalHeight), (int)arrowX, (int)(y + totalHeight));

        return y + totalHeight;
    }

    private double drawIf(IfNode node, int depth, double x, double y, double width) {
        double thenChildHeight = calculateHeight(node.getTrueNode());
        double thenRowHeight = Math.max(BOX_HEIGHT, thenChildHeight);
        double elseChildHeight = node.getFalseNode() != null ? calculateHeight(node.getFalseNode()) : 0;
        double elseRowHeight = node.getFalseNode() != null ? Math.max(BOX_HEIGHT, elseChildHeight) : 0;
        double totalHeight = thenRowHeight + elseRowHeight;

        double conditionWidth = width * 0.35;
        double arrowWidth = 20;  // Width for arrow part
        double pennantX = x + conditionWidth;  // Pennant area starts after condition text
        double arrowX = pennantX + conditionWidth - arrowWidth;  // Arrow starts here

        // Draw condition text on far left (original PADtools style)
        drawCenteredText(node.getText(), x, y, conditionWidth, totalHeight, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line at pennant left edge (connects all arrows)
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.drawLine((int)pennantX, (int)y, (int)pennantX, (int)(y + totalHeight));

        // Draw top border line
        g2d.drawLine((int)pennantX, (int)y, (int)arrowX, (int)y);

        // Draw then branch arrow shape (chevron pointing right)
        double thenMidY = y + thenRowHeight / 2;
        g2d.draw(new Line2D.Double(arrowX, y, arrowX + arrowWidth, thenMidY));
        g2d.draw(new Line2D.Double(arrowX + arrowWidth, thenMidY, arrowX, y + thenRowHeight));

        // Draw vertical line connecting to then children (at arrow tip)
        if (node.getTrueNode() != null && thenChildHeight > 0) {
            double lineX = arrowX + arrowWidth;
            g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + thenRowHeight));
            drawNode(node.getTrueNode(), depth + 1, y);
        }

        // Draw else branch if present
        if (node.getFalseNode() != null) {
            double elseY = y + thenRowHeight;

            // Draw else branch arrow shape (chevron pointing right)
            double elseMidY = elseY + elseRowHeight / 2;
            g2d.draw(new Line2D.Double(arrowX, elseY, arrowX + arrowWidth, elseMidY));
            g2d.draw(new Line2D.Double(arrowX + arrowWidth, elseMidY, arrowX, elseY + elseRowHeight));

            // Draw else label
            drawCenteredText("else", pennantX, elseY, arrowX - pennantX, elseRowHeight, TEXT_COLOR, MAIN_FONT);

            // Draw vertical line connecting to else children (at arrow tip)
            if (elseChildHeight > 0) {
                double lineX = arrowX + arrowWidth;
                g2d.drawLine((int)lineX, (int)elseY, (int)lineX, (int)(elseY + elseRowHeight));
            }

            drawNode(node.getFalseNode(), depth + 1, elseY);
        }

        // Draw bottom border line
        g2d.drawLine((int)pennantX, (int)(y + totalHeight), (int)arrowX, (int)(y + totalHeight));

        return y + totalHeight;
    }

    private double drawLoop(LoopNode node, int depth, double x, double y, double width) {
        double childHeight = calculateHeight(node.getChildNode());
        double boxHeight = Math.max(BOX_HEIGHT, childHeight + BOX_HEIGHT);

        // Draw loop condition box (original PADtools style)
        Rectangle2D rect = new Rectangle2D.Double(x, y, width, BOX_HEIGHT);
        g2d.setColor(FILL_COLOR);
        g2d.fill(rect);
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.draw(rect);

        drawCenteredText(node.getText(), x, y, width, BOX_HEIGHT, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line connecting to children
        if (node.getChildNode() != null && childHeight > 0) {
            double lineX = x + width;
            g2d.setColor(STROKE_COLOR);
            g2d.setStroke(new BasicStroke(1.5f));
            g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + boxHeight));

            drawNode(node.getChildNode(), depth + 1, y + BOX_HEIGHT);
        }

        return y + boxHeight;
    }

    private void drawCenteredText(String text, double x, double y, double width, double height,
                                  Color color, Font font) {
        g2d.setFont(font);
        g2d.setColor(color);
        FontMetrics metrics = g2d.getFontMetrics(font);

        // Wrap text if needed
        List<String> lines = wrapText(text, width - TEXT_PADDING * 2, metrics);

        // Calculate total text height
        double totalTextHeight = lines.size() * LINE_HEIGHT;
        double startY = y + (height - totalTextHeight) / 2 + metrics.getAscent();

        // Draw each line centered
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            double textX = x + (width - metrics.stringWidth(line)) / 2;
            double textY = startY + i * LINE_HEIGHT;
            g2d.drawString(line, (float)textX, (float)textY);
        }
    }

    // Draw text with wrapping, returning actual height used
    private double drawWrappedText(String text, double x, double y, double width,
                                   Color color, Font font) {
        g2d.setFont(font);
        g2d.setColor(color);
        FontMetrics metrics = g2d.getFontMetrics(font);

        List<String> lines = wrapText(text, width - TEXT_PADDING * 2, metrics);
        double boxHeight = Math.max(BOX_HEIGHT, lines.size() * LINE_HEIGHT + TEXT_PADDING * 2);

        double startY = y + TEXT_PADDING + metrics.getAscent();
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            double textX = x + (width - metrics.stringWidth(line)) / 2;
            double textY = startY + i * LINE_HEIGHT;
            g2d.drawString(line, (float)textX, (float)textY);
        }

        return boxHeight;
    }
}
