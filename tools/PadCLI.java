/**
 * PadCLI - PADtools CLI wrapper for headless PNG/SVG export
 *
 * Usage: java -cp PadTools.jar:libs/* PadCLI input.spd output.png [scale]
 *
 * This wrapper bypasses the GUI initialization and directly calls Converter.
 */

import padtools.converter.Converter;
import java.io.File;

public class PadCLI {
    public static void main(String[] args) {
        if (args.length < 2) {
            System.err.println("Usage: java -cp PadTools.jar:libs/* PadCLI input.spd output.png [scale]");
            System.err.println("  input.spd  : Input SPD file");
            System.err.println("  output.png : Output PNG file");
            System.err.println("  scale      : Image scale factor (default: 2.0)");
            System.exit(1);
        }

        File fileIn = new File(args[0]);
        File fileOut = new File(args[1]);
        Double scale = args.length > 2 ? Double.parseDouble(args[2]) : 2.0;

        if (!fileIn.exists()) {
            System.err.println("Error: Input file not found: " + fileIn.getAbsolutePath());
            System.exit(1);
        }

        try {
            Converter.convert(fileIn, fileOut, scale);
            System.out.println("Generated: " + fileOut.getAbsolutePath());
        } catch (Exception e) {
            System.err.println("Error during conversion: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
}
