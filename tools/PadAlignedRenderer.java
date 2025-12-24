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
    private static final int COLUMN_GAP = 8;
    private static final int ROW_GAP = 4;
    private static final int BAR_WIDTH = 6;  // For call box double lines
    private static final int TERMINAL_RADIUS = 16;

    // Fonts
    private static final Font MAIN_FONT = new Font("Hiragino Kaku Gothic ProN", Font.PLAIN, 12);

    // Colors
    private static final Color STROKE_COLOR = Color.BLACK;
    private static final Color FILL_COLOR = Color.WHITE;
    private static final Color TEXT_COLOR = Color.BLACK;

    // Layout state
    private Map<Integer, Double> columnWidths = new HashMap<>();
    private Map<Integer, Double> columnX = new HashMap<>();
    private Graphics2D g2d;
    private FontMetrics fm;
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
            // Call box needs extra space for double bars
            width = Math.max(BOX_MIN_WIDTH, textWidth + BAR_WIDTH * 4 + 16);
        } else if (node instanceof TerminalNode) {
            // Terminal (ellipse) needs extra padding
            width = Math.max(BOX_MIN_WIDTH, textWidth + TERMINAL_RADIUS * 2 + 8);
        } else if (node instanceof SwitchNode || node instanceof IfNode) {
            // Switch/If: condition text + case labels + arrow
            SwitchNode sw = node instanceof SwitchNode ? (SwitchNode) node : null;
            double maxCaseWidth = 0;
            if (sw != null) {
                for (String caseLabel : sw.getCases().keySet()) {
                    maxCaseWidth = Math.max(maxCaseWidth, fm.stringWidth(caseLabel));
                }
            } else {
                maxCaseWidth = fm.stringWidth("else");  // For If nodes
            }
            width = Math.max(BOX_MIN_WIDTH, textWidth + maxCaseWidth + 60);
        } else {
            // Regular process/comment nodes
            width = Math.max(BOX_MIN_WIDTH, textWidth + 16);
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

    // No text wrapping - always single line
    private List<String> wrapText(String text, double maxWidth, FontMetrics metrics) {
        List<String> lines = new ArrayList<>();
        lines.add(text == null ? "" : text);
        return lines;
    }

    // Fixed box height - no wrapping
    private double getTextBoxHeight(String text, double maxWidth) {
        return BOX_HEIGHT;
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
                NodeBase caseChild = entry.getValue();
                double childHeight = calculateHeight(caseChild);
                // Each case row: max of BOX_HEIGHT or child height
                height += Math.max(BOX_HEIGHT, childHeight);
            }
            return height;
        } else if (node instanceof IfNode) {
            IfNode ifNode = (IfNode) node;
            double thenChildHeight = calculateHeight(ifNode.getTrueNode());
            double thenHeight = Math.max(BOX_HEIGHT, thenChildHeight);
            double elseChildHeight = ifNode.getFalseNode() != null ? calculateHeight(ifNode.getFalseNode()) : 0;
            double elseHeight = ifNode.getFalseNode() != null ? Math.max(BOX_HEIGHT, elseChildHeight) : 0;
            return thenHeight + elseHeight;
        } else if (node instanceof WithChildNode) {
            WithChildNode wc = (WithChildNode) node;
            double childHeight = calculateHeight(wc.getChildNode());
            return Math.max(BOX_HEIGHT, childHeight);
        } else {
            return BOX_HEIGHT;
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

        // Draw ellipse (original PADtools style)
        Ellipse2D ellipse = new Ellipse2D.Double(x, y, width, BOX_HEIGHT);
        g2d.setColor(FILL_COLOR);
        g2d.fill(ellipse);
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.draw(ellipse);

        drawCenteredText(text, x, y, width, BOX_HEIGHT, TEXT_COLOR, MAIN_FONT);
        return y + BOX_HEIGHT;
    }

    private double drawComment(CommentNode node, double x, double y, double width) {
        String text = "(" + node.getText() + ")";  // Original PADtools style: parentheses

        // No box, just text with parentheses (original PADtools style)
        drawCenteredText(text, x, y, width, BOX_HEIGHT, TEXT_COLOR, MAIN_FONT);
        return y + BOX_HEIGHT;
    }

    private double drawCall(CallNode node, int depth, double x, double y, double width) {
        String text = node.getText();
        double childHeight = calculateHeight(node.getChildNode());
        double totalHeight = Math.max(BOX_HEIGHT, childHeight);

        // Draw call box with double vertical bars (original PADtools style)
        Rectangle2D rect = new Rectangle2D.Double(x, y, width, BOX_HEIGHT);
        g2d.setColor(FILL_COLOR);
        g2d.fill(rect);
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.draw(rect);

        // Draw double vertical bars on left and right
        g2d.drawLine((int)(x + BAR_WIDTH), (int)y, (int)(x + BAR_WIDTH), (int)(y + BOX_HEIGHT));
        g2d.drawLine((int)(x + width - BAR_WIDTH), (int)y,
                     (int)(x + width - BAR_WIDTH), (int)(y + BOX_HEIGHT));

        drawCenteredText(text, x + BAR_WIDTH, y,
                        width - BAR_WIDTH * 2, BOX_HEIGHT, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line connecting to children (on right side of box)
        if (node.getChildNode() != null && childHeight > 0) {
            double lineX = x + width;
            g2d.setColor(STROKE_COLOR);
            g2d.setStroke(new BasicStroke(1.5f));
            g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + totalHeight));

            drawNode(node.getChildNode(), depth + 1, y);
        }

        return y + totalHeight;
    }

    private double drawProcess(ProcessNode node, int depth, double x, double y, double width) {
        String text = node.getText();
        double childHeight = calculateHeight(node.getChildNode());
        double totalHeight = Math.max(BOX_HEIGHT, childHeight);

        // Draw process box (original PADtools style: simple rectangle)
        Rectangle2D rect = new Rectangle2D.Double(x, y, width, BOX_HEIGHT);
        g2d.setColor(FILL_COLOR);
        g2d.fill(rect);
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.draw(rect);

        drawCenteredText(text, x, y, width, BOX_HEIGHT, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line connecting to children (on right side of box)
        if (node.getChildNode() != null && childHeight > 0) {
            double lineX = x + width;
            g2d.setColor(STROKE_COLOR);
            g2d.setStroke(new BasicStroke(1.5f));
            g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + totalHeight));

            drawNode(node.getChildNode(), depth + 1, y);
        }

        return y + totalHeight;
    }

    private double drawSwitch(SwitchNode node, int depth, double x, double y, double width) {
        LinkedHashMap<String, NodeBase> cases = node.getCases();

        // Layout: [condition] | [case label] > [children]
        double conditionWidth = width * 0.4;
        double caseWidth = width * 0.6;
        double arrowWidth = 15;

        // Calculate total height
        double totalHeight = 0;
        for (Map.Entry<String, NodeBase> entry : cases.entrySet()) {
            NodeBase caseChild = entry.getValue();
            double childHeight = calculateHeight(caseChild);
            totalHeight += Math.max(BOX_HEIGHT, childHeight);
        }

        // Draw condition text on far left
        drawCenteredText(node.getText(), x, y, conditionWidth, totalHeight, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line at condition right edge
        double lineX = x + conditionWidth;
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + totalHeight));

        // Draw each case
        double caseY = y;
        double caseX = x + conditionWidth;
        double arrowX = caseX + caseWidth - arrowWidth;
        double arrowTipX = caseX + caseWidth;

        for (Map.Entry<String, NodeBase> entry : cases.entrySet()) {
            String caseLabel = entry.getKey();
            NodeBase caseChild = entry.getValue();
            double childHeight = calculateHeight(caseChild);
            double rowHeight = Math.max(BOX_HEIGHT, childHeight);

            // Draw top line for this case
            g2d.drawLine((int)caseX, (int)caseY, (int)arrowTipX, (int)caseY);

            // Draw arrow shape (chevron)
            double arrowMidY = caseY + rowHeight / 2;
            g2d.draw(new Line2D.Double(arrowX, caseY, arrowTipX, arrowMidY));
            g2d.draw(new Line2D.Double(arrowTipX, arrowMidY, arrowX, caseY + rowHeight));

            // Draw case label
            drawCenteredText(caseLabel, caseX, caseY, caseWidth - arrowWidth, rowHeight, TEXT_COLOR, MAIN_FONT);

            // Draw bottom line for this case
            g2d.drawLine((int)caseX, (int)(caseY + rowHeight), (int)arrowTipX, (int)(caseY + rowHeight));

            // Draw vertical line to children and draw children
            if (caseChild != null && childHeight > 0) {
                g2d.drawLine((int)arrowTipX, (int)caseY, (int)arrowTipX, (int)(caseY + rowHeight));
                drawNode(caseChild, depth + 1, caseY);
            }

            caseY += rowHeight;
        }

        return y + totalHeight;
    }

    private double drawIf(IfNode node, int depth, double x, double y, double width) {
        double thenChildHeight = calculateHeight(node.getTrueNode());
        double thenRowHeight = Math.max(BOX_HEIGHT, thenChildHeight);
        double elseChildHeight = node.getFalseNode() != null ? calculateHeight(node.getFalseNode()) : 0;
        double elseRowHeight = node.getFalseNode() != null ? Math.max(BOX_HEIGHT, elseChildHeight) : 0;
        double totalHeight = thenRowHeight + elseRowHeight;

        // Layout: [condition] | [then/else] > [children]
        double conditionWidth = width * 0.4;
        double branchWidth = width * 0.6;
        double arrowWidth = 15;

        // Draw condition text on far left
        drawCenteredText(node.getText(), x, y, conditionWidth, totalHeight, TEXT_COLOR, MAIN_FONT);

        // Draw vertical line at condition right edge
        double lineX = x + conditionWidth;
        g2d.setColor(STROKE_COLOR);
        g2d.setStroke(new BasicStroke(1.5f));
        g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + totalHeight));

        double branchX = x + conditionWidth;
        double arrowX = branchX + branchWidth - arrowWidth;
        double arrowTipX = branchX + branchWidth;

        // Draw then branch
        // Top line
        g2d.drawLine((int)branchX, (int)y, (int)arrowTipX, (int)y);

        // Arrow shape
        double thenMidY = y + thenRowHeight / 2;
        g2d.draw(new Line2D.Double(arrowX, y, arrowTipX, thenMidY));
        g2d.draw(new Line2D.Double(arrowTipX, thenMidY, arrowX, y + thenRowHeight));

        // Then label (empty or "then")
        drawCenteredText("", branchX, y, branchWidth - arrowWidth, thenRowHeight, TEXT_COLOR, MAIN_FONT);

        // Bottom line
        g2d.drawLine((int)branchX, (int)(y + thenRowHeight), (int)arrowTipX, (int)(y + thenRowHeight));

        // Vertical line to children
        if (node.getTrueNode() != null && thenChildHeight > 0) {
            g2d.drawLine((int)arrowTipX, (int)y, (int)arrowTipX, (int)(y + thenRowHeight));
            drawNode(node.getTrueNode(), depth + 1, y);
        }

        // Draw else branch if present
        if (node.getFalseNode() != null) {
            double elseY = y + thenRowHeight;

            // Arrow shape
            double elseMidY = elseY + elseRowHeight / 2;
            g2d.draw(new Line2D.Double(arrowX, elseY, arrowTipX, elseMidY));
            g2d.draw(new Line2D.Double(arrowTipX, elseMidY, arrowX, elseY + elseRowHeight));

            // Else label
            drawCenteredText("else", branchX, elseY, branchWidth - arrowWidth, elseRowHeight, TEXT_COLOR, MAIN_FONT);

            // Bottom line
            g2d.drawLine((int)branchX, (int)(elseY + elseRowHeight), (int)arrowTipX, (int)(elseY + elseRowHeight));

            // Vertical line to children
            if (elseChildHeight > 0) {
                g2d.drawLine((int)arrowTipX, (int)elseY, (int)arrowTipX, (int)(elseY + elseRowHeight));
            }

            drawNode(node.getFalseNode(), depth + 1, elseY);
        }

        return y + totalHeight;
    }

    private double drawLoop(LoopNode node, int depth, double x, double y, double width) {
        double childHeight = calculateHeight(node.getChildNode());
        double totalHeight = Math.max(BOX_HEIGHT, childHeight + BOX_HEIGHT);

        // Draw loop condition box
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
            g2d.drawLine((int)lineX, (int)y, (int)lineX, (int)(y + totalHeight));
            drawNode(node.getChildNode(), depth + 1, y + BOX_HEIGHT);
        }

        return y + totalHeight;
    }

    private void drawCenteredText(String text, double x, double y, double width, double height,
                                  Color color, Font font) {
        if (text == null || text.isEmpty()) return;

        g2d.setFont(font);
        g2d.setColor(color);
        FontMetrics metrics = g2d.getFontMetrics(font);

        // Single line, centered
        double textX = x + (width - metrics.stringWidth(text)) / 2;
        double textY = y + (height - metrics.getHeight()) / 2 + metrics.getAscent();
        g2d.drawString(text, (float)textX, (float)textY);
    }
}
