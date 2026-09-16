/* SPDX-License-Identifier: GPL-3.0-only
 * Headless probe of UNMODIFIED Sulkan release classes; no parser/frame stubs.
 * Uses reflection so the probe can be compiled with Java 17 and run with Java 25.
 * Requires the user's Sulkan 0.4.2, Minecraft 26.2 and their runtime libraries.
 */
import java.nio.file.*;
import java.util.*;
import java.lang.reflect.*;
import com.google.gson.*;

public class LoaderProbe {
    static Object call(Object target, String name, Class<?>[] types, Object... args) throws Exception {
        try { return target.getClass().getMethod(name, types).invoke(target, args); }
        catch (InvocationTargetException e) { throw new RuntimeException(name, e.getCause()); }
    }
    static Object field(Object target, String name) throws Exception { return call(target, name, new Class<?>[0]); }
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        Path archive = Path.of(args[0]);
        Path output = Path.of(args[1]);
        Files.createDirectories(output);
        Class<?> filesClass = Class.forName("com.sulkan.shaders.graph.PackFiles");
        Class<?> graphClass = Class.forName("com.sulkan.shaders.graph.PackGraph");
        Object files = filesClass.getMethod("read", Path.class).invoke(null, archive);
        String manifest = (String)call(files, "text", new Class<?>[]{String.class}, "sulkan.json");
        Object graph = graphClass.getMethod("parse", String.class).invoke(null, manifest);
        Class<?> scannerClass=Class.forName("com.sulkan.shaders.pack.ShaderPackScanner");
        Method scan=scannerClass.getDeclaredMethod("scanDirectory",Path.class);scan.setAccessible(true);
        Path isolated=Files.createTempDirectory("aurora-scanner-");
        try {
            Files.copy(archive,isolated.resolve(archive.getFileName()));
            Object scanResult=scan.invoke(null,isolated);
            List<?> supported=(List<?>)field(scanResult,"supportedPacks");
            List<?> unsupported=(List<?>)field(scanResult,"unsupportedPacks");
            if(supported.size()!=1 || !unsupported.isEmpty())throw new AssertionError("Release scanner rejected archive: "+scanResult);
        } finally {
            Files.deleteIfExists(isolated.resolve(archive.getFileName()));Files.deleteIfExists(isolated);
        }
        Map<String, Double> defaults = (Map<String, Double>)field(graph, "options");
        Map<String, Object> definitions = (Map<String, Object>)field(graph, "optionDefinitions");
        int validChoices = 0;
        for (var entry : definitions.entrySet()) {
            for (Double value : (List<Double>)field(entry.getValue(), "values")) {
                call(graph, "withOptions", new Class<?>[]{Map.class}, Map.of(entry.getKey(), value));
                validChoices++;
            }
        }
        LinkedHashMap<String, Map<String, Double>> cases = new LinkedHashMap<>();
        cases.put("default", Map.of());
        cases.put("minimal", Map.of("SHADOW_QUALITY",0.0,"AO_QUALITY",0.0,"BLOOM_STRENGTH",0.0,"WATER_ENABLED",0.0,"VEGETATION_WIND",0.0,"SUNSET_GLOW",0.0,"HEIGHT_FOG",0.0));
        cases.put("enhanced", Map.of("SHADOW_QUALITY",2.0,"SHADOW_DISTANCE",96.0,"AO_QUALITY",2.0,"EDGE_SMOOTHING",1.0,"WATER_WAVES",1.0));
        cases.put("all-maximum", new LinkedHashMap<>());
        for (var entry : definitions.entrySet()) {
            List<Double> values = (List<Double>)field(entry.getValue(), "values");
            cases.get("all-maximum").put(entry.getKey(), Collections.max(values));
        }
        for(int shadow=0;shadow<=3;shadow++) for(int water=0;water<=1;water++)
            cases.put("shadow-"+shadow+"-water-"+water, Map.of("SHADOW_QUALITY",(double)shadow,"WATER_ENABLED",(double)water));
        cases.put("ao-disabled", Map.of("AO_QUALITY",0.0));
        cases.put("ao-zero-strength", Map.of("AO_QUALITY",2.0,"AO_STRENGTH",0.0));
        cases.put("ao-eight-samples", Map.of("AO_QUALITY",2.0));
        cases.put("bloom-disabled", Map.of("BLOOM_STRENGTH",0.0));
        cases.put("edge-smoothing", Map.of("EDGE_SMOOTHING",1.0));
        cases.put("bloom-off-edge-on", Map.of("BLOOM_STRENGTH",0.0,"EDGE_SMOOTHING",1.0));
        cases.put("cave-visibility-off", Map.of("CAVE_VISIBILITY",0.0));
        cases.put("wet-surfaces-off", Map.of("WET_SURFACES",0.0));
        cases.put("dithering-off", Map.of("DITHERING",0.0));
        cases.put("sunset-glow-off", Map.of("SUNSET_GLOW",0.0));
        cases.put("height-fog-off", Map.of("HEIGHT_FOG",0.0));
        cases.put("atmosphere-off", Map.of("SUNSET_GLOW",0.0,"HEIGHT_FOG",0.0));
        // Isolate the new atmospheric terms for pixel comparisons without AO or legacy haze.
        cases.put("atmosphere-test-on", Map.of("AO_QUALITY",0.0,"FOG_STRENGTH",0.0,"SUNSET_GLOW",1.0,"HEIGHT_FOG",1.0));
        cases.put("atmosphere-test-off", Map.of("AO_QUALITY",0.0,"FOG_STRENGTH",0.0,"SUNSET_GLOW",0.0,"HEIGHT_FOG",0.0));
        cases.put("atmosphere-test-raised", Map.of("AO_QUALITY",0.0,"FOG_STRENGTH",0.0,"SUNSET_GLOW",1.0,"HEIGHT_FOG",1.0,"FOG_HEIGHT",128.0));
        List<Object> reportCases = new ArrayList<>();
        List<Object> shaders = new ArrayList<>();
        for (var test : cases.entrySet()) {
            Object selected = call(graph,"withOptions",new Class<?>[]{Map.class},test.getValue());
            Map<String,Double> options = (Map<String,Double>)field(selected,"options");
            List<?> schedule = (List<?>)field(selected,"schedule");
            List<String> passNames = new ArrayList<>();
            LinkedHashMap<String, Object> entries = new LinkedHashMap<>();
            for(Object pass : schedule) {
                String fragment=(String)field(pass,"fragment");
                passNames.add((String)field(pass,"name"));
                entries.put(fragment,field(pass,"reads"));
            }
            if (test.getKey().equals("minimal") && schedule.size()!=2)
                throw new AssertionError("Disabled AO/bloom passes were not pruned");
            for(Object program:(List<?>)field(selected,"scenePrograms")) {
                entries.put((String)field(program,"vertex"),Map.of());
                entries.put((String)field(program,"fragment"),field(program,"textures"));
            }
            Path caseDir=output.resolve(test.getKey());Files.createDirectories(caseDir);
            for(var entry:entries.entrySet()) {
                String source=(String)call(files,"shader",new Class<?>[]{String.class,Map.class},entry.getKey(),options);
                String filename=entry.getKey().replace('/','_');
                Path target=caseDir.resolve(filename);Files.writeString(target,source);
                shaders.add(Map.of("case",test.getKey(),"entry",entry.getKey(),"source",target.toString(),"reads",entry.getValue()));
            }
            List<Object> allocations=new ArrayList<>();
            for(int[] size:List.of(new int[]{1280,720},new int[]{1920,1080},new int[]{2560,1440},new int[]{3840,2160})) {
                long bytes=(Long)call(selected,"allocationBytes",new Class<?>[]{int.class,int.class},size[0],size[1]);
                allocations.add(Map.of("width",size[0],"height",size[1],"graphTargetBytes",bytes));
            }
            reportCases.add(Map.of("name",test.getKey(),"overrides",test.getValue(),"passes",passNames,"allocations",allocations));
        }
        // Read the actual loader-generated fullscreen vertex source, without creating a renderer.
        Class<?> renderer=Class.forName("com.sulkan.shaders.graph.GraphRenderer",false,LoaderProbe.class.getClassLoader());
        Field vertex=renderer.getDeclaredField("VERTEX");vertex.setAccessible(true);
        Files.writeString(output.resolve("fullscreen.vert"),(String)vertex.get(null));
        Map<String,Object> report=new LinkedHashMap<>();
        report.put("loader","Sulkan 0.4.2 release classes, unmodified");
        report.put("packFilesRead","PASS");report.put("packGraphParse","PASS");
        report.put("shaderPackScanner","PASS");
        report.put("optionChoiceCount",validChoices);report.put("cases",reportCases);report.put("shaders",shaders);
        report.put("inGameTested",false);
        Gson gson=new GsonBuilder().setPrettyPrinting().create();
        Files.writeString(output.resolve("loader-probe.json"),gson.toJson(report)+"\n");
        System.out.println("PASS: release PackFiles.read + PackGraph.parse; " + validChoices + " legal choices; " + cases.size()+" scenarios; "+shaders.size()+" expanded entrypoints.");
    }
}
