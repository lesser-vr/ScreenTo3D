#pragma once

#include <functional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace depthsbs::test {

using TestFunction = std::function<void()>;
using TestCase = std::pair<std::string, TestFunction>;

std::vector<TestCase>& registry();

struct Registrar {
    Registrar(std::string name, TestFunction function);
};

inline void require(const bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

}  // namespace depthsbs::test

#define DEPTHSBS_TEST_CONCAT_INNER(a, b) a##b
#define DEPTHSBS_TEST_CONCAT(a, b) DEPTHSBS_TEST_CONCAT_INNER(a, b)
#define DEPTHSBS_TEST(name)                                                        \
    static void DEPTHSBS_TEST_CONCAT(test_function_, __LINE__)();                  \
    static ::depthsbs::test::Registrar DEPTHSBS_TEST_CONCAT(test_registrar_,       \
                                                             __LINE__)(             \
        name, DEPTHSBS_TEST_CONCAT(test_function_, __LINE__));                     \
    static void DEPTHSBS_TEST_CONCAT(test_function_, __LINE__)()
