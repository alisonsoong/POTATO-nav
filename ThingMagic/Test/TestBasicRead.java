import com.thingmagic.Reader;
import com.thingmagic.ReaderException;
import com.thingmagic.SerialReader;
import com.thingmagic.SimpleReadPlan;
import com.thingmagic.TagProtocol;
import com.thingmagic.TagReadData;
import com.thingmagic.TMConstants;
import java.io.File;
import java.io.FileReader;
import java.io.BufferedReader;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Set;

public class TestBasicRead {
    static class Config {
        String uri = "tmr:///COM4";
        int antenna = 1;
        int durationMs = 5000;
        String outPath = defaultOutPath();
        String addlistPath = "../addlist.csv";
        boolean useAddlist = true;
        boolean raw = false;
    }

    public static void main(String[] args) {
        Config cfg = parseArgs(args);
        Reader reader = null;
        PrintWriter out = null;
        try {
            Set<String> addlist = cfg.useAddlist ? loadAddlist(cfg.addlistPath) : new HashSet<String>();
            out = createOutputWriter(cfg.outPath);
            reader = Reader.create(cfg.uri);
            connectWithBaudFallback(reader);
            configureRegionAndPlan(reader, cfg.antenna);
            applyRawMode(reader, cfg.raw);

            TagReadData[] reads = reader.read(cfg.durationMs);
            for (TagReadData tr : reads) {
                String epc = tr.epcString();
                if (cfg.useAddlist && !addlist.contains(epc)) {
                    continue;
                }
                long ts = System.currentTimeMillis();
                int ant = safeInt(() -> tr.getAntenna(), -1);
                int rssi = safeInt(() -> tr.getRssi(), -1);
                int readCount = safeInt(() -> tr.getReadCount(), -1);
                String line =
                    "timestamp_ms=" + ts
                        + ", EPC=" + epc
                        + ", antenna=" + ant
                        + ", rssi=" + rssi
                        + ", read_count=" + readCount;
                System.out.println(line);
                out.println(line);
            }
            System.out.println("Saved results to: " + cfg.outPath);
        } catch (Exception e) {
            System.err.println("Failed to read from reader at " + cfg.uri + ": " + e.getMessage());
            System.err.println("Check COM port, permissions, and that no other app is holding the reader.");
        } finally {
            if (out != null) {
                out.close();
            }
            if (reader != null) {
                reader.destroy();
            }
        }
    }

    private static void configureRegionAndPlan(Reader reader, int antenna) throws Exception {
        try {
            reader.paramSet(TMConstants.TMR_PARAM_REGION_ID, Reader.Region.NA);
        } catch (ReaderException re) {
            Object current = reader.paramGet(TMConstants.TMR_PARAM_REGION_ID);
            if (current != Reader.Region.NA) {
                throw re;
            }
        }
        SimpleReadPlan plan = new SimpleReadPlan(new int[]{antenna}, TagProtocol.GEN2, null, null, 1000);
        reader.paramSet(TMConstants.TMR_PARAM_READ_PLAN, plan);
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
            } else if ("--no-addlist".equalsIgnoreCase(a)) {
                cfg.useAddlist = false;
            } else if ("--raw".equalsIgnoreCase(a)) {
                cfg.raw = true;
            } else {
                System.err.println("Ignoring unknown/incomplete arg: " + a);
            }
        }
        return cfg;
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
        return "../Results/TestBasicRead_" + new SimpleDateFormat("yyyyMMdd_HHmmss").format(new Date()) + ".csv";
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
