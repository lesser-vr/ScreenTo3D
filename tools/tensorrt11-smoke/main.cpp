#include <NvInfer.h>
#include <NvInferRuntime.h>
#include <NvOnnxParser.h>

#include <chrono>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {

class Logger final : public nvinfer1::ILogger {
public:
    void log(const Severity severity, const char* message) noexcept override {
        if (severity <= Severity::kWARNING) std::cerr << "TensorRT: " << message << '\n';
    }
};

template <typename T>
using TrtPointer = std::unique_ptr<T>;

template <typename T>
TrtPointer<T> require(T* pointer, const char* message) {
    if (pointer == nullptr) throw std::runtime_error(message);
    return TrtPointer<T>(pointer);
}

std::string escape_json(const std::string& value) {
    std::string result;
    result.reserve(value.size());
    for (const char character : value) {
        if (character == '"' || character == '\\') result.push_back('\\');
        result.push_back(character);
    }
    return result;
}

void report_parser_errors(const nvonnxparser::IParser& parser) {
    for (int32_t index = 0; index < parser.getNbErrors(); ++index) {
        const auto* error = parser.getError(index);
        if (error != nullptr) std::cerr << "ONNX parser: " << error->desc() << '\n';
    }
}

}  // namespace

int main(const int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: depthsbs_tensorrt11_smoke <model.onnx> <engine.plan>\n";
        return 2;
    }

    const std::filesystem::path model_path(argv[1]);
    const std::filesystem::path engine_path(argv[2]);
    if (!std::filesystem::is_regular_file(model_path)) return 2;

    try {
        Logger logger;
        const auto started = std::chrono::steady_clock::now();
        auto builder = require(nvinfer1::createInferBuilder(logger), "builder creation failed");
        auto network = require(builder->createNetworkV2(0U), "network creation failed");
        auto parser = require(nvonnxparser::createParser(*network, logger),
                              "ONNX parser creation failed");
        if (!parser->parseFromFile(model_path.string().c_str(),
                                   static_cast<int32_t>(nvinfer1::ILogger::Severity::kWARNING))) {
            report_parser_errors(*parser);
            throw std::runtime_error("ONNX parsing failed");
        }

        auto config = require(builder->createBuilderConfig(), "builder config creation failed");
        config->setMemoryPoolLimit(nvinfer1::MemoryPoolType::kWORKSPACE,
                                   256ULL * 1024ULL * 1024ULL);
        auto serialized = require(builder->buildSerializedNetwork(*network, *config),
                                  "serialized engine build failed");
        if (serialized->size() == 0) throw std::runtime_error("serialized engine is empty");

        auto runtime = require(nvinfer1::createInferRuntime(logger), "runtime creation failed");
        auto engine = require(runtime->deserializeCudaEngine(serialized->data(), serialized->size()),
                              "fresh engine deserialization failed");
        if (engine->getNbIOTensors() != 2) throw std::runtime_error("unexpected I/O tensor count");
        const bool fp16_io =
            engine->getTensorDataType("input") == nvinfer1::DataType::kHALF &&
            engine->getTensorDataType("output") == nvinfer1::DataType::kHALF;
        if (!fp16_io) throw std::runtime_error("engine I/O is not FP16");

        std::filesystem::create_directories(engine_path.parent_path());
        auto temporary_path = engine_path;
        temporary_path += ".partial";
        {
            std::ofstream output(temporary_path, std::ios::binary | std::ios::trunc);
            if (!output) throw std::runtime_error("temporary engine open failed");
            output.write(static_cast<const char*>(serialized->data()),
                         static_cast<std::streamsize>(serialized->size()));
            output.flush();
            if (!output) throw std::runtime_error("serialized engine write failed");
        }
        if (std::filesystem::exists(engine_path)) std::filesystem::remove(engine_path);
        std::filesystem::rename(temporary_path, engine_path);

        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - started);
        std::cout << "{\n"
                  << "  \"schema_version\": 1,\n"
                  << "  \"model\": \"" << escape_json(model_path.string()) << "\",\n"
                  << "  \"engine\": \"" << escape_json(engine_path.string()) << "\",\n"
                  << "  \"engine_bytes\": " << serialized->size() << ",\n"
                  << "  \"io_tensors\": " << engine->getNbIOTensors() << ",\n"
                  << "  \"build_ms\": " << elapsed.count() << ",\n"
                  << "  \"fp16_io\": true,\n"
                  << "  \"deserialization_validated\": true,\n"
                  << "  \"atomic_publication\": true\n"
                  << "}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
