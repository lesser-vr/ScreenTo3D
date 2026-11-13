#include "screento3d/foundation/capabilities.h"

#include <iomanip>
#include <sstream>
#include <string_view>

namespace screento3d {
namespace {

std::string escape_json(std::string_view value) {
    std::ostringstream output;
    for (const unsigned char character : value) {
        switch (character) {
            case '"': output << "\\\""; break;
            case '\\': output << "\\\\"; break;
            case '\b': output << "\\b"; break;
            case '\f': output << "\\f"; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;
            default:
                if (character < 0x20) {
                    output << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                           << static_cast<int>(character) << std::dec;
                } else {
                    output << character;
                }
        }
    }
    return output.str();
}

void write_component(std::ostringstream& output,
                     std::string_view name,
                     const ComponentCapability& component,
                     std::string_view indent,
                     std::string_view child_indent,
                     bool trailing_comma,
                     bool pretty) {
    const auto newline = pretty ? "\n" : "";
    const auto separator = pretty ? " " : "";
    output << indent << '"' << name << "\":" << separator << '{' << newline
           << child_indent << "\"availability\":" << separator << '"'
           << to_string(component.availability) << "\"," << newline
           << child_indent << "\"version\":" << separator << '"'
           << escape_json(component.version) << "\"," << newline
           << child_indent << "\"diagnostic\":" << separator << '"'
           << escape_json(component.diagnostic) << '"' << newline
           << indent << '}' << (trailing_comma ? "," : "") << newline;
}

}  // namespace

std::string_view to_string(const Availability availability) noexcept {
    switch (availability) {
        case Availability::available: return "available";
        case Availability::unavailable: return "unavailable";
        case Availability::unknown: return "unknown";
    }
    return "unknown";
}

std::string to_json(const SystemCapabilities& capabilities, const bool pretty) {
    const auto newline = pretty ? "\n" : "";
    const auto separator = pretty ? " " : "";
    const auto indent = pretty ? "  " : "";
    const auto child_indent = pretty ? "    " : "";

    std::ostringstream output;
    output << '{' << newline
           << indent << "\"schema_version\":" << separator << '"'
           << escape_json(capabilities.schema_version) << "\"," << newline
           << indent << "\"platform\":" << separator << '"'
           << escape_json(capabilities.platform) << "\"," << newline;

    write_component(output, "nvidia_driver", capabilities.nvidia_driver, indent,
                    child_indent, true, pretty);
    write_component(output, "cuda_driver", capabilities.cuda_driver, indent,
                    child_indent, true, pretty);
    write_component(output, "nvdec_loader", capabilities.nvdec_loader, indent,
                    child_indent, true, pretty);
    write_component(output, "nvenc_loader", capabilities.nvenc_loader, indent,
                    child_indent, true, pretty);
    write_component(output, "tensorrt", capabilities.tensorrt, indent,
                    child_indent, true, pretty);
    write_component(output, "ffmpeg", capabilities.ffmpeg, indent,
                    child_indent, true, pretty);
    write_component(output, "ffprobe", capabilities.ffprobe, indent,
                    child_indent, true, pretty);

    output << indent << "\"gpus\":" << separator << '[';
    if (!capabilities.gpus.empty()) {
        output << newline;
    }
    for (std::size_t index = 0; index < capabilities.gpus.size(); ++index) {
        const auto& gpu = capabilities.gpus[index];
        output << child_indent << '{' << newline
               << (pretty ? "      " : "") << "\"ordinal\":" << separator
               << gpu.ordinal << ',' << newline
               << (pretty ? "      " : "") << "\"name\":" << separator << '"'
               << escape_json(gpu.name) << "\"," << newline
               << (pretty ? "      " : "") << "\"compute_capability\":" << separator
               << '"' << gpu.compute_major << '.' << gpu.compute_minor << "\"," << newline
               << (pretty ? "      " : "") << "\"total_memory_bytes\":" << separator
               << gpu.total_memory_bytes << newline
               << child_indent << '}'
               << (index + 1 == capabilities.gpus.size() ? "" : ",") << newline;
    }
    output << (capabilities.gpus.empty() ? "" : indent) << ']' << newline << '}' << newline;
    return output.str();
}

}  // namespace screento3d
