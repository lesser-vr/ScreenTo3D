#include "depthsbs/foundation/capabilities.h"
#include "depthsbs/mode/mode_policy.h"

#include <iostream>
#include <string_view>

namespace {

void print_usage(std::ostream& output) {
    output << "DepthSBS foundation CLI\n\n"
              "Usage:\n"
              "  depthsbs capability [--compact]\n"
              "  depthsbs mode <performance|balanced|video-quality|offline-quality> "
              "[--compact]\n";
}

bool compact_requested(const int argc, char** argv) {
    for (int index = 1; index < argc; ++index) {
        if (std::string_view(argv[index]) == "--compact") return true;
    }
    return false;
}

}  // namespace

int main(const int argc, char** argv) {
    if (argc < 2) {
        print_usage(std::cerr);
        return 2;
    }

    const std::string_view command(argv[1]);
    const bool pretty = !compact_requested(argc, argv);

    if (command == "capability") {
        std::cout << depthsbs::to_json(depthsbs::probe_system_capabilities(), pretty);
        return 0;
    }

    if (command == "mode") {
        if (argc < 3) {
            std::cerr << "mode requires a mode name\n";
            print_usage(std::cerr);
            return 2;
        }
        const auto mode = depthsbs::parse_processing_mode(argv[2]);
        if (!mode.has_value()) {
            std::cerr << "unknown processing mode: " << argv[2] << '\n';
            return 2;
        }
        std::cout << depthsbs::to_json(depthsbs::resolve_processing_plan(*mode), pretty);
        return 0;
    }

    std::cerr << "unknown command: " << command << '\n';
    print_usage(std::cerr);
    return 2;
}
