import com.thingmagic.Reader;
import com.thingmagic.SerialReader;
import com.thingmagic.SimpleReadPlan;
import com.thingmagic.TagProtocol;
import com.thingmagic.TagReadData;
import com.thingmagic.TMConstants;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Arrays;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Set;

public class TestFrequencyRead {
    static class Config {
        String uri = "tmr:///COM4";
        int antenna = 1;
        int durationMs = 5000;
        String outPath = defaultOutPath();
        String addlistPath = "../addlist.csv";
        boolean raw = false;
    }

    public static void main(String[] args) {
        Config cfg = parseArgs(args);
        Reader reader = null;
        PrintWriter out = null;
        try {
            Set<String> addlist = loadAddlist(cfg.addlistPath);
            out = createOutputWriter(cfg.outPath);
            reader = Reader.create(cfg.uri);
            connectWithBaudFallback(reader);
            applyRawMode(reader, cfg.raw);
            reader.paramSet(TMConstants.TMR_PARAM_REGION_ID, Reader.Region.NA);
            reader.paramSet(
                TMConstants.TMR_PARAM_READER_METADATA,
                EnumSet.of(
                    TagReadData.TagMetadataFlag.ANTENNAID,
                    TagReadData.TagMetadataFlag.RSSI,
                    TagReadData.TagMetadataFlag.FREQUENCY,
                    TagReadData.TagMetadataFlag.PHASE
                )
            );
            reader.paramSet(TMConstants.TMR_PARAM_READ_PLAN,
                new SimpleReadPlan(new int[]{cfg.antenna}, TagProtocol.GEN2, null, null, 1000));

            printFrequencyParams(reader, out);
            tryConstrainedFrequency(reader, out);

            String header = "timestamp_ms,epc,antenna,rssi,frequency,phase";
            System.out.println(header);
            out.println(header);
            TagReadData[] reads = reader.read(cfg.durationMs);
            for (TagReadData tr : reads) {
                String epc = normalizedEpc(tr.epcString(), addlist);
                if (!matchesAddlist(epc, addlist)) {
                    continue;
                }
                String line =
                    System.currentTimeMillis() + "," +
                    epc + "," +
                    safeInt(() -> tr.getAntenna(), -1) + "," +
                    safeInt(() -> tr.getRssi(), -1) + "," +
                    safeInt(() -> tr.getFrequency(), -1) + "," +
                    safeInt(() -> tr.getPhase(), -1);
                System.out.println(line);
                out.println(line);
            }
            System.out.println("Saved results to: " + cfg.outPath);
        } catch (Exception e) {
            System.err.println("Frequency test failed: " + e.getMessage());
        } finally {
            if (out != null) {
                out.close();
            }
            if (reader != null) {
                reader.destroy();
            }
        }
    }

    private static Config parseArgs(String[] args) {
        Config cfg = new Config();
        for (int i = 0; i < args.length; i++) {
            String a = args[i];
            if ("--uri".equalsIgnoreCase(a) && i + 1 < args.length) {
                cfg.uri = args[++i];
            } else if ("--ant".equalsIgnoreCase(a) && i + 1 < args.length) {
                cfg.antenna = Integer.parseInt(args[++i]);
            } else if ("--duration".equalsIgnoreCase(a) && i + 1 < args.length) {
                cfg.durationMs = Integer.parseInt(args[++i]);
            } else if ("--out".equalsIgnoreCase(a) && i + 1 < args.length) {
                cfg.outPath = args[++i];
            } else if ("--addlist".equalsIgnoreCase(a) && i + 1 < args.length) {
                cfg.addlistPath = args[++i];
            } else if ("--raw".equalsIgnoreCase(a)) {
                cfg.raw = true;
            } else {
                System.err.println("Ignoring unknown/incomplete arg: " + a);
            }
        }
        return cfg;
    }

    private static void printFrequencyParams(Reader reader, PrintWriter out) {
        // Frequency-related params vary by region/model/firmware; probe defensively.
        printParam(reader, out, "region", TMConstants.TMR_PARAM_REGION_ID);
        printParam(reader, out, "hopTable", TMConstants.TMR_PARAM_REGION_HOPTABLE);
        printParam(reader, out, "hopTime", TMConstants.TMR_PARAM_REGION_HOPTIME);
        printParam(reader, out, "minimumFrequency", TMConstants.TMR_PARAM_REGION_MINIMUM_FREQUENCY);
        printParam(reader, out, "quantizationStep", TMConstants.TMR_PARAM_REGION_QUANTIZATION_STEP);
        printParam(reader, out, "dwellTimeEnable", TMConstants.TMR_PARAM_REGION_DWELL_TIME_ENABLE);
        printParam(reader, out, "dwellTime", TMConstants.TMR_PARAM_REGION_DWELL_TIME);
    }

    private static void tryConstrainedFrequency(Reader reader, PrintWriter out) {
        // Fixed/constrained frequency behavior is region and firmware dependent.
        try {
            int[] currentHopTable = (int[]) reader.paramGet(TMConstants.TMR_PARAM_REGION_HOPTABLE);
            if (currentHopTable != null && currentHopTable.length > 0) {
                int keep = currentHopTable[0];
                reader.paramSet(TMConstants.TMR_PARAM_REGION_HOPTABLE, new int[]{keep});
                String msg = "Constrained hop table to single entry: " + keep + " kHz";
                System.out.println(msg);
                out.println(msg);
            } else {
                String msg = "Hop table unavailable or empty; leaving defaults.";
                System.out.println(msg);
                out.println(msg);
            }
        } catch (Exception ex) {
            String msg = "Could not constrain frequency (continuing normally): " + ex.getMessage();
            System.out.println(msg);
            out.println(msg);
        }
    }

    private static void printParam(Reader reader, PrintWriter out, String label, String key) {
        try {
            Object val = reader.paramGet(key);
            String msg;
            if (val instanceof int[]) {
                msg = label + " (" + key + "): " + Arrays.toString((int[]) val);
            } else {
                msg = label + " (" + key + "): " + val;
            }
            System.out.println(msg);
            out.println(msg);
        } catch (Exception ex) {
            String msg = label + " (" + key + "): unsupported (" + ex.getMessage() + ")";
            System.out.println(msg);
            out.println(msg);
        }
    }

    private static void connectWithBaudFallback(Reader reader) throws Exception {
        try {
            reader.connect();
        } catch (Exception ex) {
            if (reader instanceof SerialReader && ex.getMessage() != null && ex.getMessage().contains("Timeout")) {
                int[] currentBaudRate = new int[1];
                ((SerialReader) reader).probeBaudRate(currentBaudRate);
                reader.paramSet(TMConstants.TMR_PARAM_BAUDRATE, currentBaudRate[0]);
                reader.connect();
            } else {
                throw ex;
            }
        }
    }

    interface IntSupplier {
        int get() throws Exception;
    }

    private static int safeInt(IntSupplier supplier, int fallback) {
        try {
            return supplier.get();
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private static String defaultOutPath() {
        return "../Results/TestFrequencyRead_" + new SimpleDateFormat("yyyyMMdd_HHmmss").format(new Date()) + ".csv";
    }

    private static PrintWriter createOutputWriter(String path) throws Exception {
        File f = new File(path);
        File parent = f.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new Exception("Could not create output directory: " + parent.getPath());
        }
        return new PrintWriter(new FileWriter(f, true), true);
    }

    private static Set<String> loadAddlist(String path) throws Exception {
        Set<String> addlist = new HashSet<String>();
        BufferedReader br = new BufferedReader(new FileReader(path));
        try {
            String line;
            while ((line = br.readLine()) != null) {
                String v = line.trim();
                if (v.isEmpty() || v.startsWith("#")) {
                    continue;
                }
                addlist.add(v);
            }
        } finally {
            br.close();
        }
        if (addlist.isEmpty()) {
            throw new Exception("addlist is empty: " + path);
        }
        System.out.println("Loaded addlist entries: " + addlist.size() + " from " + path);
        return addlist;
    }

    private static boolean matchesAddlist(String epc, Set<String> addlist) {
        return addlist.contains(epc);
    }

    private static String normalizedEpc(String raw, Set<String> addlist) {
        if (raw == null) {
            return "";
        }
        if (addlist.contains(raw)) {
            return raw;
        }
        if (raw.length() > 4) {
            String stripped = raw.substring(4);
            if (addlist.contains(stripped)) {
                return stripped;
            }
        }
        return raw;
    }

    private static void applyRawMode(Reader reader, boolean raw) {
        if (!raw) {
            return;
        }
        try {
            reader.paramSet(TMConstants.TMR_PARAM_ENABLE_READ_FILTERING, false);
            System.out.println("Raw mode enabled: /reader/tagReadData/enableReadFilter=false");
        } catch (Exception ex) {
            System.out.println("Raw mode requested but not applied: " + ex.getMessage());
        }
    }
}
