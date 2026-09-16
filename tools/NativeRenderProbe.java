/* SPDX-License-Identifier: GPL-3.0-only
 * Offscreen Vulkan pixel probe for the release-compiled post-processing SPIR-V.
 * Synthetic textures only: this does not launch Minecraft or measure game FPS.
 * Compile with Java 17 + LWJGL Vulkan/core + Gson. Run with Java 25.
 */
import java.nio.*;
import java.nio.file.*;
import java.util.*;
import com.google.gson.*;
import org.lwjgl.PointerBuffer;
import org.lwjgl.system.*;
import org.lwjgl.vulkan.*;
import static org.lwjgl.vulkan.VK10.*;

public class NativeRenderProbe implements AutoCloseable {
    VkInstance instance;
    VkPhysicalDevice physical;
    VkDevice device;
    VkQueue queue;
    long commandPool;
    int queueFamily;
    String deviceName;
    int deviceType;
    record Buffer(long handle, long memory, long size) {}
    record Image(long handle, long memory, long view, int width, int height) {}

    static void check(int status) {
        if (status != VK_SUCCESS) throw new IllegalStateException("Vulkan status " + status);
    }

    NativeRenderProbe() {
        try (MemoryStack s = MemoryStack.stackPush()) {
            VkApplicationInfo app = VkApplicationInfo.calloc(s).sType$Default()
                .pApplicationName(s.UTF8("UN Aurora synthetic pixel checks"))
                .apiVersion(VK_MAKE_VERSION(1, 2, 0));
            VkInstanceCreateInfo ci = VkInstanceCreateInfo.calloc(s).sType$Default().pApplicationInfo(app);
            PointerBuffer out = s.mallocPointer(1);
            check(vkCreateInstance(ci, null, out));
            instance = new VkInstance(out.get(0), ci);
            IntBuffer count = s.ints(0);
            check(vkEnumeratePhysicalDevices(instance, count, null));
            if (count.get(0) == 0) throw new IllegalStateException("No Vulkan devices");
            PointerBuffer devices = s.mallocPointer(count.get(0));
            check(vkEnumeratePhysicalDevices(instance, count, devices));
            physical = new VkPhysicalDevice(devices.get(0), instance);
            VkPhysicalDeviceProperties props = VkPhysicalDeviceProperties.calloc(s);
            vkGetPhysicalDeviceProperties(physical, props);
            deviceName = props.deviceNameString(); deviceType = props.deviceType();
            vkGetPhysicalDeviceQueueFamilyProperties(physical, count, null);
            VkQueueFamilyProperties.Buffer families = VkQueueFamilyProperties.calloc(count.get(0), s);
            vkGetPhysicalDeviceQueueFamilyProperties(physical, count, families);
            queueFamily = -1;
            for (int i = 0; i < families.capacity(); i++)
                if ((families.get(i).queueFlags() & VK_QUEUE_GRAPHICS_BIT) != 0) { queueFamily = i; break; }
            if (queueFamily < 0) throw new IllegalStateException("No graphics queue");
            VkDeviceQueueCreateInfo.Buffer queues = VkDeviceQueueCreateInfo.calloc(1, s);
            queues.get(0).sType$Default().queueFamilyIndex(queueFamily).pQueuePriorities(s.floats(1));
            VkDeviceCreateInfo dc = VkDeviceCreateInfo.calloc(s).sType$Default().pQueueCreateInfos(queues);
            check(vkCreateDevice(physical, dc, null, out));
            device = new VkDevice(out.get(0), physical, dc);
            vkGetDeviceQueue(device, queueFamily, 0, out); queue = new VkQueue(out.get(0), device);
            LongBuffer handle = s.longs(0);
            check(vkCreateCommandPool(device, VkCommandPoolCreateInfo.calloc(s).sType$Default()
                .queueFamilyIndex(queueFamily), null, handle));
            commandPool = handle.get(0);
        }
    }

    int memoryType(int bits, int flags) {
        try (MemoryStack s = MemoryStack.stackPush()) {
            VkPhysicalDeviceMemoryProperties props = VkPhysicalDeviceMemoryProperties.calloc(s);
            vkGetPhysicalDeviceMemoryProperties(physical, props);
            for (int i = 0; i < props.memoryTypeCount(); i++)
                if ((bits & (1 << i)) != 0 && (props.memoryTypes(i).propertyFlags() & flags) == flags) return i;
            throw new IllegalStateException("No suitable memory type");
        }
    }

    Buffer buffer(long size, int usage) {
        try (MemoryStack s = MemoryStack.stackPush()) {
            LongBuffer handle = s.longs(0);
            check(vkCreateBuffer(device, VkBufferCreateInfo.calloc(s).sType$Default().size(size)
                .usage(usage).sharingMode(VK_SHARING_MODE_EXCLUSIVE), null, handle));
            long b = handle.get(0);
            VkMemoryRequirements req = VkMemoryRequirements.calloc(s);
            vkGetBufferMemoryRequirements(device, b, req);
            check(vkAllocateMemory(device, VkMemoryAllocateInfo.calloc(s).sType$Default()
                .allocationSize(req.size()).memoryTypeIndex(memoryType(req.memoryTypeBits(),
                    VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)), null, handle));
            check(vkBindBufferMemory(device, b, handle.get(0), 0));
            return new Buffer(b, handle.get(0), size);
        }
    }

    void upload(Buffer b, byte[] data) {
        if (data.length != b.size) throw new IllegalArgumentException("Buffer size mismatch");
        try (MemoryStack s = MemoryStack.stackPush()) {
            PointerBuffer p = s.mallocPointer(1);
            check(vkMapMemory(device, b.memory, 0, b.size, 0, p));
            MemoryUtil.memByteBuffer(p.get(0), data.length).put(data);
            vkUnmapMemory(device, b.memory);
        }
    }

    Image image(int width, int height, int format, int usage) {
        try (MemoryStack s = MemoryStack.stackPush()) {
            LongBuffer handle = s.longs(0);
            VkImageCreateInfo ci = VkImageCreateInfo.calloc(s).sType$Default()
                .imageType(VK_IMAGE_TYPE_2D).format(format).mipLevels(1).arrayLayers(1)
                .samples(VK_SAMPLE_COUNT_1_BIT).tiling(VK_IMAGE_TILING_OPTIMAL)
                .usage(usage).sharingMode(VK_SHARING_MODE_EXCLUSIVE).initialLayout(VK_IMAGE_LAYOUT_UNDEFINED);
            ci.extent().set(width, height, 1);
            check(vkCreateImage(device, ci, null, handle)); long im = handle.get(0);
            VkMemoryRequirements req = VkMemoryRequirements.calloc(s); vkGetImageMemoryRequirements(device, im, req);
            check(vkAllocateMemory(device, VkMemoryAllocateInfo.calloc(s).sType$Default()
                .allocationSize(req.size()).memoryTypeIndex(memoryType(req.memoryTypeBits(),
                    VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)), null, handle));
            long memory = handle.get(0); check(vkBindImageMemory(device, im, memory, 0));
            VkImageViewCreateInfo vc = VkImageViewCreateInfo.calloc(s).sType$Default()
                .image(im).viewType(VK_IMAGE_VIEW_TYPE_2D).format(format);
            vc.subresourceRange().aspectMask(VK_IMAGE_ASPECT_COLOR_BIT).levelCount(1).layerCount(1);
            check(vkCreateImageView(device, vc, null, handle));
            return new Image(im, memory, handle.get(0), width, height);
        }
    }

    static void transition(VkCommandBuffer command, Image image, int oldLayout, int newLayout,
                           int srcAccess, int dstAccess, int srcStage, int dstStage) {
        try (MemoryStack s = MemoryStack.stackPush()) {
            VkImageMemoryBarrier.Buffer barrier = VkImageMemoryBarrier.calloc(1, s);
            barrier.get(0).sType$Default().oldLayout(oldLayout).newLayout(newLayout)
                .srcAccessMask(srcAccess).dstAccessMask(dstAccess)
                .srcQueueFamilyIndex(VK_QUEUE_FAMILY_IGNORED).dstQueueFamilyIndex(VK_QUEUE_FAMILY_IGNORED)
                .image(image.handle);
            barrier.get(0).subresourceRange().aspectMask(VK_IMAGE_ASPECT_COLOR_BIT).levelCount(1).layerCount(1);
            vkCmdPipelineBarrier(command, srcStage, dstStage, 0, null, null, barrier);
        }
    }

    long shader(Path path) throws Exception {
        byte[] bytes = Files.readAllBytes(path);
        ByteBuffer data = MemoryUtil.memAlloc(bytes.length); data.put(bytes).flip();
        try (MemoryStack s = MemoryStack.stackPush()) {
            LongBuffer out = s.longs(0);
            check(vkCreateShaderModule(device, VkShaderModuleCreateInfo.calloc(s).sType$Default().pCode(data), null, out));
            return out.get(0);
        } finally { MemoryUtil.memFree(data); }
    }

    void destroy(Buffer b) { vkDestroyBuffer(device, b.handle, null); vkFreeMemory(device, b.memory, null); }
    void destroy(Image i) { vkDestroyImageView(device, i.view, null); vkDestroyImage(device, i.handle, null); vkFreeMemory(device, i.memory, null); }

    void draw(JsonObject job) throws Exception {
        int width = job.get("width").getAsInt(), height = job.get("height").getAsInt();
        boolean unorm = job.get("unorm").getAsBoolean();
        int format = unorm ? VK_FORMAT_R8G8B8A8_UNORM : VK_FORMAT_R32G32B32A32_SFLOAT;
        List<Image> inputs = new ArrayList<>(); List<Buffer> staging = new ArrayList<>();
        List<Long> samplers = new ArrayList<>();
        Buffer frame = buffer(656, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT);
        upload(frame, Files.readAllBytes(Path.of(job.get("frame").getAsString())));
        Image output = image(width, height, format, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
        Buffer download = buffer((long)width * height * (unorm ? 4 : 16), VK_BUFFER_USAGE_TRANSFER_DST_BIT);
        try (MemoryStack s = MemoryStack.stackPush()) {
            LongBuffer out = s.longs(0);
            JsonArray textures = job.getAsJsonArray("textures");
            for (JsonElement entry : textures) {
                JsonObject t = entry.getAsJsonObject();
                int w = t.get("width").getAsInt(), h = t.get("height").getAsInt();
                Image im = image(w, h, VK_FORMAT_R32G32B32A32_SFLOAT, VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT);
                inputs.add(im);
                Buffer b = buffer((long)w*h*16, VK_BUFFER_USAGE_TRANSFER_SRC_BIT); staging.add(b);
                upload(b, Files.readAllBytes(Path.of(t.get("path").getAsString())));
                int filter = t.get("linear").getAsBoolean() ? VK_FILTER_LINEAR : VK_FILTER_NEAREST;
                check(vkCreateSampler(device, VkSamplerCreateInfo.calloc(s).sType$Default()
                    .magFilter(filter).minFilter(filter).mipmapMode(VK_SAMPLER_MIPMAP_MODE_NEAREST)
                    .addressModeU(VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE).addressModeV(VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE)
                    .addressModeW(VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE).maxLod(0), null, out));
                samplers.add(out.get(0));
            }
            VkDescriptorSetLayoutBinding.Buffer bindings = VkDescriptorSetLayoutBinding.calloc(1+inputs.size(), s);
            bindings.get(0).binding(0).descriptorType(VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER).descriptorCount(1).stageFlags(VK_SHADER_STAGE_FRAGMENT_BIT);
            for (int i=0; i<inputs.size(); i++) bindings.get(i+1).binding(i+1)
                .descriptorType(VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER).descriptorCount(1).stageFlags(VK_SHADER_STAGE_FRAGMENT_BIT);
            check(vkCreateDescriptorSetLayout(device, VkDescriptorSetLayoutCreateInfo.calloc(s).sType$Default().pBindings(bindings), null, out));
            long setLayout = out.get(0);
            check(vkCreatePipelineLayout(device, VkPipelineLayoutCreateInfo.calloc(s).sType$Default().pSetLayouts(s.longs(setLayout)), null, out));
            long pipelineLayout = out.get(0);
            VkDescriptorPoolSize.Buffer sizes = VkDescriptorPoolSize.calloc(2, s);
            sizes.get(0).type(VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER).descriptorCount(1);
            sizes.get(1).type(VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER).descriptorCount(inputs.size());
            check(vkCreateDescriptorPool(device, VkDescriptorPoolCreateInfo.calloc(s).sType$Default().maxSets(1).pPoolSizes(sizes), null, out));
            long descriptorPool = out.get(0);
            check(vkAllocateDescriptorSets(device, VkDescriptorSetAllocateInfo.calloc(s).sType$Default()
                .descriptorPool(descriptorPool).pSetLayouts(s.longs(setLayout)), out));
            long descriptorSet = out.get(0);
            VkWriteDescriptorSet.Buffer writes = VkWriteDescriptorSet.calloc(1+inputs.size(), s);
            writes.get(0).sType$Default().dstSet(descriptorSet).dstBinding(0).descriptorType(VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER)
                .descriptorCount(1).pBufferInfo(VkDescriptorBufferInfo.calloc(1,s).buffer(frame.handle).offset(0).range(frame.size));
            for (int i=0; i<inputs.size(); i++) writes.get(i+1).sType$Default().dstSet(descriptorSet).dstBinding(i+1)
                .descriptorType(VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER).descriptorCount(1)
                .pImageInfo(VkDescriptorImageInfo.calloc(1,s).sampler(samplers.get(i)).imageView(inputs.get(i).view)
                    .imageLayout(VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL));
            vkUpdateDescriptorSets(device, writes, null);
            VkAttachmentDescription.Buffer attachment = VkAttachmentDescription.calloc(1,s).format(format)
                .samples(VK_SAMPLE_COUNT_1_BIT).loadOp(VK_ATTACHMENT_LOAD_OP_CLEAR).storeOp(VK_ATTACHMENT_STORE_OP_STORE)
                .stencilLoadOp(VK_ATTACHMENT_LOAD_OP_DONT_CARE).stencilStoreOp(VK_ATTACHMENT_STORE_OP_DONT_CARE)
                .initialLayout(VK_IMAGE_LAYOUT_UNDEFINED).finalLayout(VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL);
            VkAttachmentReference.Buffer ref = VkAttachmentReference.calloc(1,s).attachment(0).layout(VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL);
            VkSubpassDescription.Buffer subpass = VkSubpassDescription.calloc(1,s).pipelineBindPoint(VK_PIPELINE_BIND_POINT_GRAPHICS)
                .colorAttachmentCount(1).pColorAttachments(ref);
            VkSubpassDependency.Buffer dependencies = VkSubpassDependency.calloc(2,s);
            dependencies.get(0).srcSubpass(VK_SUBPASS_EXTERNAL).dstSubpass(0).srcStageMask(VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT)
                .dstStageMask(VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT).dstAccessMask(VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
            dependencies.get(1).srcSubpass(0).dstSubpass(VK_SUBPASS_EXTERNAL).srcStageMask(VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT)
                .dstStageMask(VK_PIPELINE_STAGE_TRANSFER_BIT).srcAccessMask(VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT).dstAccessMask(VK_ACCESS_TRANSFER_READ_BIT);
            check(vkCreateRenderPass(device, VkRenderPassCreateInfo.calloc(s).sType$Default()
                .pAttachments(attachment).pSubpasses(subpass).pDependencies(dependencies), null, out));
            long renderPass = out.get(0);
            check(vkCreateFramebuffer(device, VkFramebufferCreateInfo.calloc(s).sType$Default().renderPass(renderPass)
                .pAttachments(s.longs(output.view)).width(width).height(height).layers(1), null, out));
            long framebuffer = out.get(0);
            long vertex = shader(Path.of(job.get("vertex").getAsString()));
            long fragment = shader(Path.of(job.get("fragment").getAsString()));
            VkPipelineShaderStageCreateInfo.Buffer stages = VkPipelineShaderStageCreateInfo.calloc(2,s);
            stages.get(0).sType$Default().stage(VK_SHADER_STAGE_VERTEX_BIT).module(vertex).pName(s.UTF8("main"));
            stages.get(1).sType$Default().stage(VK_SHADER_STAGE_FRAGMENT_BIT).module(fragment).pName(s.UTF8("main"));
            VkViewport.Buffer viewport = VkViewport.calloc(1,s).width(width).height(height).minDepth(0).maxDepth(1);
            VkRect2D.Buffer scissor = VkRect2D.calloc(1,s); scissor.get(0).extent().set(width,height);
            VkPipelineColorBlendAttachmentState.Buffer blend = VkPipelineColorBlendAttachmentState.calloc(1,s).colorWriteMask(15);
            VkGraphicsPipelineCreateInfo.Buffer pipelineInfo = VkGraphicsPipelineCreateInfo.calloc(1,s);
            pipelineInfo.get(0).sType$Default().pStages(stages)
                .pVertexInputState(VkPipelineVertexInputStateCreateInfo.calloc(s).sType$Default())
                .pInputAssemblyState(VkPipelineInputAssemblyStateCreateInfo.calloc(s).sType$Default().topology(VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST))
                .pViewportState(VkPipelineViewportStateCreateInfo.calloc(s).sType$Default().pViewports(viewport).pScissors(scissor))
                .pRasterizationState(VkPipelineRasterizationStateCreateInfo.calloc(s).sType$Default().polygonMode(VK_POLYGON_MODE_FILL)
                    .cullMode(VK_CULL_MODE_NONE).frontFace(VK_FRONT_FACE_COUNTER_CLOCKWISE).lineWidth(1))
                .pMultisampleState(VkPipelineMultisampleStateCreateInfo.calloc(s).sType$Default().rasterizationSamples(VK_SAMPLE_COUNT_1_BIT))
                .pColorBlendState(VkPipelineColorBlendStateCreateInfo.calloc(s).sType$Default().pAttachments(blend))
                .layout(pipelineLayout).renderPass(renderPass).subpass(0);
            check(vkCreateGraphicsPipelines(device,VK_NULL_HANDLE,pipelineInfo,null,out)); long pipeline=out.get(0);
            PointerBuffer pointer=s.mallocPointer(1);
            check(vkAllocateCommandBuffers(device,VkCommandBufferAllocateInfo.calloc(s).sType$Default()
                .commandPool(commandPool).level(VK_COMMAND_BUFFER_LEVEL_PRIMARY).commandBufferCount(1),pointer));
            VkCommandBuffer command=new VkCommandBuffer(pointer.get(0),device);
            check(vkBeginCommandBuffer(command,VkCommandBufferBeginInfo.calloc(s).sType$Default()));
            for(int i=0;i<inputs.size();i++) {
                Image im=inputs.get(i);
                transition(command,im,VK_IMAGE_LAYOUT_UNDEFINED,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,0,VK_ACCESS_TRANSFER_WRITE_BIT,
                    VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT);
                VkBufferImageCopy.Buffer copy=VkBufferImageCopy.calloc(1,s);
                copy.get(0).imageSubresource().aspectMask(VK_IMAGE_ASPECT_COLOR_BIT).layerCount(1);
                copy.get(0).imageExtent().set(im.width,im.height,1);
                vkCmdCopyBufferToImage(command,staging.get(i).handle,im.handle,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,copy);
                transition(command,im,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                    VK_ACCESS_TRANSFER_WRITE_BIT,VK_ACCESS_SHADER_READ_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
            }
            VkRenderPassBeginInfo begin=VkRenderPassBeginInfo.calloc(s).sType$Default().renderPass(renderPass).framebuffer(framebuffer)
                .pClearValues(VkClearValue.calloc(1,s));
            begin.renderArea().extent().set(width,height);
            vkCmdBeginRenderPass(command,begin,VK_SUBPASS_CONTENTS_INLINE);
            vkCmdBindPipeline(command,VK_PIPELINE_BIND_POINT_GRAPHICS,pipeline);
            vkCmdBindDescriptorSets(command,VK_PIPELINE_BIND_POINT_GRAPHICS,pipelineLayout,0,s.longs(descriptorSet),null);
            vkCmdDraw(command,3,1,0,0);vkCmdEndRenderPass(command);
            VkBufferImageCopy.Buffer copy=VkBufferImageCopy.calloc(1,s);
            copy.get(0).imageSubresource().aspectMask(VK_IMAGE_ASPECT_COLOR_BIT).layerCount(1);
            copy.get(0).imageExtent().set(width,height,1);
            vkCmdCopyImageToBuffer(command,output.handle,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,download.handle,copy);
            VkMemoryBarrier.Buffer host=VkMemoryBarrier.calloc(1,s).sType$Default()
                .srcAccessMask(VK_ACCESS_TRANSFER_WRITE_BIT).dstAccessMask(VK_ACCESS_HOST_READ_BIT);
            vkCmdPipelineBarrier(command,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,host,null,null);
            check(vkEndCommandBuffer(command));
            check(vkCreateFence(device,VkFenceCreateInfo.calloc(s).sType$Default(),null,out));long fence=out.get(0);
            VkSubmitInfo submit=VkSubmitInfo.calloc(s).sType$Default().pCommandBuffers(s.pointers(command.address()));
            check(vkQueueSubmit(queue,submit,fence));check(vkWaitForFences(device,fence,true,60_000_000_000L));
            check(vkMapMemory(device,download.memory,0,download.size,0,pointer));
            byte[] pixels=new byte[(int)download.size];MemoryUtil.memByteBuffer(pointer.get(0),pixels.length).get(pixels);
            vkUnmapMemory(device,download.memory);Files.write(Path.of(job.get("output").getAsString()),pixels);
            vkDestroyFence(device,fence,null);vkFreeCommandBuffers(device,commandPool,command);
            vkDestroyPipeline(device,pipeline,null);vkDestroyShaderModule(device,vertex,null);vkDestroyShaderModule(device,fragment,null);
            vkDestroyFramebuffer(device,framebuffer,null);vkDestroyRenderPass(device,renderPass,null);
            vkDestroyDescriptorPool(device,descriptorPool,null);vkDestroyPipelineLayout(device,pipelineLayout,null);vkDestroyDescriptorSetLayout(device,setLayout,null);
        }
        for(long sampler:samplers)vkDestroySampler(device,sampler,null);
        for(Image i:inputs)destroy(i);for(Buffer b:staging)destroy(b);
        destroy(output);destroy(download);destroy(frame);
        System.out.println("DRAW PASS: "+job.get("name").getAsString());
    }

    public void close() {
        if(device!=null){vkDeviceWaitIdle(device);vkDestroyCommandPool(device,commandPool,null);vkDestroyDevice(device,null);}
        if(instance!=null)vkDestroyInstance(instance,null);
    }

    public static void main(String[] args) throws Exception {
        Path config=Path.of(args[0]);JsonObject jobs=JsonParser.parseString(Files.readString(config)).getAsJsonObject();
        try(NativeRenderProbe probe=new NativeRenderProbe()) {
            System.out.println("Vulkan device: "+probe.deviceName);
            for(JsonElement job:jobs.getAsJsonArray("jobs"))probe.draw(job.getAsJsonObject());
            Map<String,Object> report=new LinkedHashMap<>();
            report.put("device",probe.deviceName);report.put("deviceType",probe.deviceType);
            report.put("vulkanDeviceCreated",true);report.put("draws",jobs.getAsJsonArray("jobs").size());
            report.put("input","Synthetic textures; release-compiled post-processing modules");
            report.put("inGameTested",false);report.put("fpsMeasured",false);
            Files.writeString(config.resolveSibling("vulkan-render.json"),new GsonBuilder().setPrettyPrinting().create().toJson(report)+"\n");
        }
    }
}
