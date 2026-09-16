/* SPDX-License-Identifier: GPL-3.0-only
 * Compile and reflect with Sulkan 0.4.2's unmodified NativeShaderCompiler and
 * Minecraft 26.2's IntermediaryShaderModule; no VkDevice or game is created.
 */
import java.nio.*;
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import com.google.gson.*;

public class NativeCompileProbe {
    static Object property(Object value, String name) throws Exception {
        Method method=value.getClass().getDeclaredMethod(name);method.setAccessible(true);
        return method.invoke(value);
    }
    static List<String> names(Object module,String kind) throws Exception {
        List<String> result=new ArrayList<>();
        for(Object value:(List<?>)property(module,kind))result.add((String)property(value,"name"));
        return result;
    }
    @SuppressWarnings({"unchecked","rawtypes"})
    public static void main(String[] args) throws Exception {
        Path folder=Path.of(args[0]);
        Path spirvFolder=folder.resolve("spirv");Files.createDirectories(spirvFolder);
        JsonObject input=JsonParser.parseString(Files.readString(folder.resolve("loader-probe.json"))).getAsJsonObject();
        Class<?> compilerClass=Class.forName("com.sulkan.shaders.runtime.NativeShaderCompiler");
        Class<?> shaderType=Class.forName("com.mojang.blaze3d.shaders.ShaderType");
        Method compile=compilerClass.getMethod("compile",String.class,String.class,shaderType);
        Object compiler=compilerClass.getConstructor().newInstance();
        Class<?> entryClass=Class.forName("com.mojang.blaze3d.vulkan.VulkanBindGroupLayout$Entry");
        Class<?> entryType=Class.forName("com.mojang.blaze3d.vulkan.VulkanBindGroupLayout$VulkanBindGroupEntryType");
        Class<?> gpuFormat=Class.forName("com.mojang.blaze3d.GpuFormat");
        Constructor<?> entryConstructor=entryClass.getConstructor(entryType,String.class,gpuFormat);
        Map<String,List<String>> geometryOutputs=new HashMap<>();
        List<Map<String,Object>> results=new ArrayList<>();
        try {
            List<JsonObject> entries=new ArrayList<>();
            for(JsonElement row:input.getAsJsonArray("shaders"))entries.add(row.getAsJsonObject());
            JsonObject fullscreen=new JsonObject();fullscreen.addProperty("case","loader");
            fullscreen.addProperty("entry","fullscreen.vert");fullscreen.addProperty("source",folder.resolve("fullscreen.vert").toString());
            fullscreen.add("reads",new JsonObject());entries.add(fullscreen);
            for(JsonObject row:entries) {
                String entry=row.get("entry").getAsString();
                String scenario=row.get("case").getAsString();
                String source=Files.readString(Path.of(row.get("source").getAsString()));
                boolean vertex=entry.endsWith(".vsh")||entry.endsWith(".vert");
                boolean geometry=entry.contains("terrain.");
                String[] variants=entry.endsWith("terrain.fsh")?new String[]{"opaque","cutout-0.1","cutout-0.5"}:new String[]{"base"};
                for(String variant:variants) {
                    String expanded=source;
                    if(variant.startsWith("cutout")) {
                        int newline=source.indexOf('\n')+1;
                        expanded=source.substring(0,newline)+"#define ALPHA_CUTOUT "+variant.substring(7)+"\n"+source.substring(newline);
                    }
                    String label=scenario+"__"+entry.replace('/','_')+"__"+variant;
                    String runtimeName=(geometry?"sulkan:native_geometry/":"sulkan:native_post/")+label;
                    Object stage=Enum.valueOf((Class<Enum>)shaderType,vertex?"VERTEX":"FRAGMENT");
                    Object module;
                    try {module=compile.invoke(compiler,runtimeName,expanded,stage);}
                    catch(InvocationTargetException e) {throw new RuntimeException("Compile failed: "+label,e.getCause());}
                    try {
                        List<String> samplers=names(module,"samplers"), uniforms=names(module,"uniformBuffers");
                        Set<String> allowed=new HashSet<>(row.getAsJsonObject("reads").keySet());
                        if(geometry)allowed.addAll(List.of("u_BlockTex","u_LightTex","u_SectionTimeInfo","Opaque","OpaqueDepth"));
                        for(int i=0;i<4;i++)allowed.add("SulkanShadowMap"+i);
                        for(int i=0;i<2;i++)allowed.add("SulkanEntityShadowMap"+i);
                        for(String sampler:samplers)if(!allowed.contains(sampler))
                            throw new AssertionError("Unbound sampler "+sampler+" in "+label);
                        Set<String> allowedBlocks=geometry?Set.of("SulkanFrame","SulkanWind","u_Globals","SulkanShadowData"):Set.of("SulkanFrame");
                        for(String block:uniforms)if(!allowedBlocks.contains(block))
                            throw new AssertionError("Unbound uniform "+block+" in "+label);
                        List<Object> bindings=new ArrayList<>();
                        for(String block:new TreeSet<>(allowedBlocks))bindings.add(entryConstructor.newInstance(
                            Enum.valueOf((Class<Enum>)entryType,"UNIFORM_BUFFER"),block,null));
                        for(String sampler:new TreeSet<>(allowed)) {
                            boolean texel=sampler.equals("u_SectionTimeInfo");
                            bindings.add(entryConstructor.newInstance(Enum.valueOf((Class<Enum>)entryType,texel?"TEXEL_BUFFER":"SAMPLED_IMAGE"),
                                sampler,texel?Enum.valueOf((Class<Enum>)gpuFormat,"R32_SINT"):null));
                        }
                        List<String> incoming;
                        if(geometry && vertex) {
                            incoming=List.of("a_Position","a_Color","a_TexCoord","a_LightAndData","a_SulkanMaterial");
                            geometryOutputs.put(scenario,names(module,"outputs"));
                        } else if(geometry) {
                            incoming=geometryOutputs.get(scenario);
                            if(incoming==null)throw new AssertionError("No vertex interface for "+scenario);
                        } else incoming=vertex?List.of():List.of("texCoord");
                        // Exercise Minecraft's actual descriptor and input-name remapping.
                        module.getClass().getMethod("rebind",List.class,List.class).invoke(module,incoming,bindings);
                        ByteBuffer buffer=((ByteBuffer)property(module,"spirv")).duplicate();
                        byte[] binary=new byte[buffer.remaining()];buffer.get(binary);
                        Path path=spirvFolder.resolve(label+".spv");Files.write(path,binary);
                        Map<String,Object> record=new LinkedHashMap<>();
                        record.put("case",scenario);record.put("entry",entry);record.put("variant",variant);
                        record.put("samplers",samplers);record.put("uniforms",uniforms);
                        record.put("inputs",names(module,"inputs"));record.put("outputs",names(module,"outputs"));
                        record.put("spirv",path.toString());record.put("bytes",binary.length);record.put("status","PASS");
                        record.put("minecraftRebind","PASS");
                        results.add(record);
                    } finally {((AutoCloseable)module).close();}
                }
            }
        } finally {((AutoCloseable)compiler).close();}
        Map<String,Object> report=new LinkedHashMap<>();
        report.put("compiler","Unmodified Sulkan 0.4.2 NativeShaderCompiler + Minecraft 26.2 SPIRV-Cross reflection");
        report.put("target","Vulkan 1.2");report.put("moduleCount",results.size());report.put("modules",results);
        report.put("vulkanDeviceCreated",false);report.put("inGameTested",false);
        Files.writeString(folder.resolve("native-compile.json"),new GsonBuilder().setPrettyPrinting().create().toJson(report)+"\n");
        System.out.println("PASS: "+results.size()+" shader modules compiled and reflected by the release compiler; all samplers/uniforms bound.");
    }
}
