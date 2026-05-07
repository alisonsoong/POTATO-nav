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
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Set;

public class TestTwoAntennaRead {
    static class Config {
        String uri = "tmr:///COM4";
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

            try {
                reader.paramSet(TMConstants.TMR_PARAM_TAGREADDATA_UNIQUEBYANTENNA, true);
                String msg = "Enabled /reader/tagReadData/uniqueByAntenna=true";
                System.out.println(msg);
                out.println(msg);
            } catch (Exception ex) {
                String msg = "Could not enable uniqueByAntenna (continuing): " + ex.getMessage();
                System.out.println(msg);
                out.println(msg);
            }

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
                new SimpleReadPlan(new int[]{1, 2}, TagProtocol.GEN2, null, null, 1000));

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
            System.err.println("Two-antenna read failed: " + e.getMessage());
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
        return "../Results/TestTwoAntennaRead_" + new SimpleDateFormat("yyyyMMdd_HHmmss").format(new Date()) + ".csv";
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
