#include "test_support.h"

#include <exception>
#include <iostream>

namespace depthsbs::test {

std::vector<TestCase>& registry() {
    static std::vector<TestCase> tests;
    return tests;
}

Registrar::Registrar(std::string name, TestFunction function) {
    registry().emplace_back(std::move(name), std::move(function));
}

}  // namespace depthsbs::test

int main() {
    int failures = 0;
    for (const auto& [name, function] : depthsbs::test::registry()) {
        try {
            function();
            std::cout << "PASS " << name << '\n';
        } catch (const std::exception& error) {
            ++failures;
            std::cerr << "FAIL " << name << ": " << error.what() << '\n';
        }
    }
    std::cout << depthsbs::test::registry().size() << " test(s), " << failures
              << " failure(s)\n";
    return failures == 0 ? 0 : 1;
}
