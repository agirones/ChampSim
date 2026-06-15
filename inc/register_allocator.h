#include <array>
#include <cstdint>
#include <list>
#include <optional>
#include <queue>

#ifndef REG_ALLOC_H
#define REG_ALLOC_H

#include "instruction.h"

enum class reg_write_kind : uint8_t {
  unknown = 0,
  gpr,
  stack_pointer,
  flags,
  instruction_pointer,
  store,
  branch,
  trace_entry,
};

struct physical_register {
  uint16_t arch_reg_index;
  uint64_t producing_instruction_id;
  bool valid; // has the producing instruction committed yet?
  bool busy;  // is this register in use anywhere in the pipeline?
  champsim::address producer_ip{};
  reg_write_kind producer_kind{reg_write_kind::unknown};
  branch_type producer_branch{NOT_BRANCH};
};

class RegisterAllocator
{
public:
  static constexpr std::size_t ZERO_READ_CATEGORY_COUNT = 14;

private:
  std::array<PHYSICAL_REGISTER_ID, std::numeric_limits<uint8_t>::max() + 1> frontend_RAT, backend_RAT;
  std::queue<PHYSICAL_REGISTER_ID> free_registers;
  std::vector<physical_register> physical_register_file;
  std::vector<uint32_t> read_counts;
  std::array<uint64_t, 4> read_before_overwrite_histogram{};
  std::array<uint64_t, ZERO_READ_CATEGORY_COUNT> zero_read_by_category{};
  uint64_t zero_read_lifetime_total{0};

  void record_lifetime_reads(PHYSICAL_REGISTER_ID physreg, uint32_t reads);
  static reg_write_kind classify_producer(const ooo_model_instr& producer, int16_t arch_reg);
  static std::size_t zero_read_category_index(const physical_register& meta);

public:
  RegisterAllocator(size_t num_physical_registers);
  PHYSICAL_REGISTER_ID rename_dest_register(int16_t reg, champsim::program_ordered<ooo_model_instr>::id_type producer_id);
  PHYSICAL_REGISTER_ID rename_dest_register(int16_t reg, const ooo_model_instr& producer, int16_t arch_reg);
  PHYSICAL_REGISTER_ID rename_src_register(int16_t reg);
  void complete_dest_register(PHYSICAL_REGISTER_ID physreg);
  void retire_dest_register(PHYSICAL_REGISTER_ID physreg);
  void free_register(PHYSICAL_REGISTER_ID physreg);
  bool isValid(PHYSICAL_REGISTER_ID physreg) const;
  bool isAllocated(PHYSICAL_REGISTER_ID archreg) const;
  unsigned long count_free_registers() const;
  int count_reg_dependencies(const ooo_model_instr& instr) const;
  void reset_frontend_RAT();
  void reset_register_lifetime_histogram();
  void print_register_lifetime_histogram() const;
  void print_zero_read_producer_breakdown() const;
  void print_deadlock();
};
#endif
